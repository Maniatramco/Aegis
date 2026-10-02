"""Credential-free contracts; these do not certify a live OCI tenancy."""
import base64
import hashlib
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from app.oci_adapters import OCIStorageAdapter, OCIQueueAdapter, OCIServiceFailure, OCIProviderUnavailable, capability_report


def storage(client=None, **kwargs):
    return OCIStorageAdapter(client=client or Mock(), namespace='ns', bucket='private', prefix='aegis', **kwargs)


def test_storage_put_contract_and_stable_key():
    client=Mock(); s=storage(client); raw=b'hello'
    s.put('documents/id/original', raw)
    client.put_object.assert_called_once_with('ns','private','aegis/documents/id/original',raw,
        content_length=5,content_type='application/octet-stream',content_md5=base64.b64encode(hashlib.md5(raw).digest()).decode(),opc_meta={'sha256':hashlib.sha256(raw).hexdigest()})
    assert s.object_key('documents/id/original')=='aegis/documents/id/original'


@pytest.mark.parametrize('key',['','/absolute','../escape','a/../b','a//b','a/./b','a\\b','a\x00b','a/'])
def test_reject_keys(key):
    with pytest.raises(ValueError): storage().get(key)


def test_json_roundtrip_and_stream_close():
    client=Mock();s=storage(client);value={'name':'München','count':2}
    s.put_json('templates/id.json',value)
    payload=client.put_object.call_args.args[3]
    body=Mock(content=payload);client.get_object.return_value=NS(data=body,headers={'opc-meta-sha256':hashlib.sha256(payload).hexdigest()})
    assert s.json('templates/id.json')==value
    body.close.assert_called_once()


def test_checksum_failure():
    client=Mock();client.get_object.return_value=NS(data=Mock(content=b'bad'),headers={'opc-meta-sha256':'wrong'})
    with pytest.raises(OCIServiceFailure,match='checksum'): storage(client).get('a')


def error(status):
    exc=RuntimeError('SECRET PRIVATE ENDPOINT');exc.status=status;return exc


def test_not_found_and_delete_idempotence():
    client=Mock();client.get_object.side_effect=error(404);client.delete_object.side_effect=error(404)
    with pytest.raises(FileNotFoundError):storage(client).get('missing')
    storage(client).delete('missing')


@pytest.mark.parametrize('status',[401,403,409,429,500])
def test_sanitized_service_errors(status):
    client=Mock();client.put_object.side_effect=error(status)
    with pytest.raises(OCIServiceFailure) as caught:storage(client).put('a',b'x')
    assert 'SECRET' not in str(caught.value)


def test_connection_read_only():
    client=Mock();result=storage(client).test_connection()
    client.head_bucket.assert_called_once_with('ns','private')
    client.put_object.assert_not_called()
    assert result=={'ok':True,'scope':'bucket_read','write_verified':False}


def test_missing_settings(monkeypatch):
    monkeypatch.delenv('OCI_NAMESPACE',raising=False);monkeypatch.delenv('OCI_BUCKET',raising=False)
    with pytest.raises(OCIProviderUnavailable):OCIStorageAdapter(client=Mock())


def test_capabilities_not_live_ready_and_independent():
    a=capability_report();a['object_storage']['ready']=True
    assert capability_report()['object_storage']['implemented']
    assert not capability_report()['object_storage']['ready']


def queue(client):
    models=NS(PutMessagesDetails=NS,PutMessagesDetailsEntry=NS,UpdateMessageDetails=NS)
    return OCIQueueAdapter(client=client,queue_id='q-id',models=models)


def test_queue_publish_receive_ack_extend():
    client=Mock();q=queue(client)
    client.put_messages.return_value=NS(data=NS(messages=[NS(id='m-id')]))
    assert q.enqueue('job-id')==['m-id']
    assert json.loads(client.put_messages.call_args.args[1].messages[0].content)=={'job_id':'job-id'}
    client.get_messages.return_value=NS(data=NS(messages=[NS(id='m-id',receipt='receipt',content='{}',delivery_count=2)]))
    assert q.dequeue()[0]['receipt']=='receipt'
    client.get_messages.assert_called_once_with('q-id',limit=1,visibility_in_seconds=900,timeout_in_seconds=20)
    q.ack('receipt');client.delete_message.assert_called_once_with('q-id','receipt')
    q.extend('receipt',120);assert client.update_message.call_args.args[2].visibility_in_seconds==120


def test_queue_connection_read_only():
    client=Mock();assert queue(client).test_connection()['publish_verified'] is False
    client.get_stats.assert_called_once_with('q-id');client.put_messages.assert_not_called()


def test_queue_does_not_accept_insecure_endpoint(monkeypatch):
    with pytest.raises(OCIProviderUnavailable):OCIQueueAdapter(queue_id='q',endpoint='http://evil.example')


def test_queue_validation():
    q=queue(Mock())
    with pytest.raises(ValueError):q.dequeue(limit=100)
    with pytest.raises(ValueError):q.extend('',900)
    with pytest.raises(ValueError):q.enqueue('')


def test_real_sdk_generated_models_and_operation_arguments():
    oci=pytest.importorskip('oci')
    from unittest.mock import patch
    config={'region':'us-chicago-1'}
    client=oci.object_storage.ObjectStorageClient(config,signer=Mock(spec=oci.auth.signers.InstancePrincipalsSecurityTokenSigner),retry_strategy=oci.retry.NoneRetryStrategy())
    with patch.object(client.base_client,'call_api',return_value=NS(data=None,headers={})) as call:
        storage(client).put('doc',b'bytes')
        assert call.call_args.kwargs['body']==b'bytes'
    qc=oci.queue.QueueClient(config,signer=Mock(spec=oci.auth.signers.InstancePrincipalsSecurityTokenSigner),service_endpoint='https://cell-1.queue.messaging.us-chicago-1.oci.oraclecloud.com',retry_strategy=oci.retry.NoneRetryStrategy())
    q=OCIQueueAdapter(client=qc,queue_id='q-id',models=oci.queue.models)
    with patch.object(qc.base_client,'call_api',return_value=NS(data=NS(messages=[NS(id='m')]),headers={})) as call:
        assert q.enqueue('job')==['m']
        assert isinstance(call.call_args.kwargs['body'],oci.queue.models.PutMessagesDetails)
        q.extend('receipt',300)
        assert isinstance(call.call_args.kwargs['body'],oci.queue.models.UpdateMessageDetails)


def test_storage_destination_config_passed_to_sdk_factory():
    from unittest.mock import patch
    with patch('app.oci_adapters._client',return_value=Mock()) as factory:
        s=OCIStorageAdapter(namespace='teamns',bucket='documents',prefix='v2',region='us-phoenix-1',auth_mode='config_file',profile='AEGIS',config_file='/run/secrets/oci/config')
        assert s.object_key('docs/1')=='v2/docs/1'
        factory.assert_called_once_with('storage',region='us-phoenix-1',auth_mode='config_file',profile='AEGIS',config_file='/run/secrets/oci/config')


def test_storage_json_probe_does_not_expose_destination():
    client=Mock();result=storage(client).test_connection()
    assert 'private' not in json.dumps(result)
    assert 'ns' not in json.dumps(result)
