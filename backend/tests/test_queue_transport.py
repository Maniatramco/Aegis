"""Credential-free queue transport contracts. No OCI network or resources."""

import json
from unittest.mock import Mock

import pytest

from app import queue_transport as module
from app.oci_adapters import OCIProviderUnavailable, OCIServiceFailure
from app.queue_transport import QueueDelivery, QueueTransport, get_transport


def adapter():
    result = Mock()
    result.enqueue.return_value = ['message-1']
    result.dequeue.return_value = []
    result.test_connection.return_value = {'ok': True, 'scope': 'queue_stats'}
    return result


def message(job_id='job-1', **overrides):
    return {'receipt': 'receipt-1', 'id': 'message-1',
            'content': json.dumps({'job_id': job_id}), 'delivery_count': 1, **overrides}


@pytest.fixture(autouse=True)
def clean_cache():
    module._transport.cache_clear()
    yield
    module._transport.cache_clear()


def test_database_default_never_initializes_oci(monkeypatch):
    monkeypatch.delenv('QUEUE_PROVIDER', raising=False)
    factory = Mock(side_effect=AssertionError('Must not initialize OCI'))
    monkeypatch.setattr(module, 'OCIQueueAdapter', factory)
    queue = get_transport()
    assert queue.provider == 'database'
    assert queue.notify('job-1')
    assert queue.receive() is None
    assert not queue.renew(QueueDelivery('job-1', 'receipt'))
    assert not queue.ack_terminal(QueueDelivery('job-1', 'receipt'), 'completed')
    assert queue.test_connection()['database_connectivity_verified'] is False
    assert queue.status()['ready'] is True
    assert queue.status()['durable_source'] == 'database'
    factory.assert_not_called()


def test_selected_provider_and_environment_cache(monkeypatch):
    monkeypatch.setenv('QUEUE_PROVIDER', 'oci')
    monkeypatch.setenv('OCI_QUEUE_ID', 'queue-1')
    first = get_transport()
    assert first.provider == 'oci'
    assert first is get_transport()
    assert get_transport('database').provider == 'database'
    monkeypatch.setenv('OCI_QUEUE_ID', 'queue-2')
    assert first is not get_transport()
    monkeypatch.setenv('QUEUE_PROVIDER', 'unrecognized')
    with pytest.raises(ValueError, match='QUEUE_PROVIDER'):
        get_transport()


def test_lazy_client_created_once_and_notify_post_commit_hook(monkeypatch):
    client = adapter()
    factory = Mock(return_value=client)
    monkeypatch.setattr(module, 'OCIQueueAdapter', factory)
    queue = get_transport('oci')
    factory.assert_not_called()
    assert module.notify_job('job-1', provider='oci')
    assert queue.notify('job-2')
    factory.assert_called_once_with()
    assert client.enqueue.call_count == 2


@pytest.mark.parametrize('job_id', ['', None, 1, 'a' * 129, ' leading', 'trailing ', 'a\n', 'job id', 'a\x00b'])
def test_invalid_job_identifier_rejected_without_publish(job_id):
    client = adapter()
    queue = QueueTransport('oci', adapter=client)
    with pytest.raises(ValueError, match='job ID'):
        queue.notify(job_id)
    client.enqueue.assert_not_called()


def test_receive_targets_one_job_and_renew_uses_receipt():
    client = adapter()
    client.dequeue.return_value = [message()]
    queue = QueueTransport('oci', adapter=client)
    notification = queue.receive()
    assert notification == QueueDelivery('job-1', 'receipt-1', 'message-1', 1)
    client.dequeue.assert_called_once_with(limit=1, visibility=900, timeout=0)
    client.ack.assert_not_called()
    assert queue.renew(notification)
    client.extend.assert_called_once_with('receipt-1', visibility=900)
    assert queue.status()['checks']['lease_renewal'] is True


@pytest.mark.parametrize('status', ['queued', 'running', 'retry', 'pending', '', None, 'missing', 'COMPLETED'])
def test_never_acknowledge_nonterminal_job(status):
    client = adapter()
    queue = QueueTransport('oci', adapter=client)
    assert queue.ack_terminal(QueueDelivery('job-1', 'receipt-1'), status) is False
    client.ack.assert_not_called()


@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled'])
def test_terminal_acknowledgement(status):
    client = adapter()
    queue = QueueTransport('oci', adapter=client)
    assert queue.ack_terminal(QueueDelivery('job-1', 'receipt-1'), status)
    client.ack.assert_called_once_with('receipt-1')


@pytest.mark.parametrize('overrides', [
    {'content': '{'}, {'content': 'null'}, {'content': '[]'},
    {'content': json.dumps({'job_id': ''})},
    {'content': json.dumps({'job_id': {'nested': 'secret'}})},
    {'content': 'x' * 4097}, {'content': b'bytes'},
    {'receipt': ''}, {'receipt': None}, {'delivery_count': 'invalid'},
])
def test_malformed_notifications_remain_unacknowledged(overrides):
    client = adapter()
    client.dequeue.return_value = [message(**overrides)]
    queue = QueueTransport('oci', adapter=client)
    assert queue.receive() is None
    client.ack.assert_not_called()
    assert queue.status()['status'] == 'degraded'
    assert queue.status()['reconciliation_required'] is True


@pytest.mark.parametrize('operation', ['enqueue', 'dequeue', 'extend', 'ack'])
def test_errors_are_best_effort_sanitized_and_do_not_claim_readiness(operation, caplog):
    client = adapter()
    getattr(client, operation).side_effect = RuntimeError('PRIVATE SECRET https://private-endpoint/?token=hidden')
    queue = QueueTransport('oci', adapter=client)
    delivery = QueueDelivery('job-1', 'private-receipt')
    result = {'enqueue': lambda: queue.notify('job-1'),
              'dequeue': lambda: queue.receive(),
              'extend': lambda: queue.renew(delivery),
              'ack': lambda: queue.ack_terminal(delivery, 'completed')}[operation]()
    assert not result
    status = queue.status()
    assert status['status'] == 'degraded'
    assert not status['ready']
    assert not status['live_verified']
    assert 'PRIVATE' not in caplog.text + json.dumps(status)
    assert 'private-endpoint' not in caplog.text + json.dumps(status)
    assert 'private-receipt' not in caplog.text + json.dumps(status)


def test_publish_without_message_id_is_not_success():
    client = adapter()
    client.enqueue.return_value = []
    queue = QueueTransport('oci', adapter=client)
    assert not queue.notify('job-1')
    assert queue.status()['checks']['publish'] is False


def test_stats_probe_never_proves_publish_or_roundtrip():
    client = adapter()
    queue = QueueTransport('oci', adapter=client)
    probe = queue.test_connection()
    assert probe['ok'] and not probe['publish_verified'] and not probe['live_verified']
    status = queue.status()
    assert status['configured'] and status['checks']['connection']
    assert status['status'] == 'unverified'
    assert not status['ready'] and not status['live_verified']
    client.dequeue.assert_not_called()
    client.enqueue.assert_not_called()


@pytest.mark.parametrize('error', [OCIProviderUnavailable('PRIVATE PATH'), RuntimeError('PRIVATE SECRET')])
def test_explicit_probe_error_is_sanitized(error):
    client = adapter()
    client.test_connection.side_effect = error
    queue = QueueTransport('oci', adapter=client)
    with pytest.raises((OCIProviderUnavailable, OCIServiceFailure)) as caught:
        queue.test_connection()
    assert 'PRIVATE' not in str(caught.value)
    assert queue.status(probe=True)['status'] == 'degraded'


def test_unrelated_operations_do_not_claim_round_trip():
    client = adapter()
    client.dequeue.return_value = [message('job-from-another-publisher')]
    queue = QueueTransport('oci', adapter=client)
    assert queue.notify('our-job')
    notification = queue.receive()
    assert queue.ack_terminal(notification, 'completed')
    assert not queue.status()['live_verified']


def test_complete_roundtrip_and_later_failure_readiness():
    client = adapter()
    client.dequeue.return_value = [message()]
    queue = QueueTransport('oci', adapter=client)
    assert queue.notify('job-1')
    delivery = queue.receive()
    assert not queue.status()['live_verified']
    assert queue.ack_terminal(delivery, 'completed')
    assert queue.status()['live_verified'] and queue.status()['ready']
    client.enqueue.side_effect = RuntimeError('outage')
    assert not queue.notify('job-2')
    # A healthy receive cannot erase a publish outage.
    assert queue.receive()
    assert not queue.status()['ready']
    client.enqueue.side_effect = None
    assert queue.notify('job-2')
    assert queue.status()['ready']


def test_status_is_passive_and_missing_config_not_ready(monkeypatch):
    monkeypatch.delenv('OCI_QUEUE_ID', raising=False)
    monkeypatch.delenv('OCI_QUEUE_ENDPOINT', raising=False)
    factory = Mock(side_effect=AssertionError('Must not inspect credentials'))
    monkeypatch.setattr(module, 'OCIQueueAdapter', factory)
    queue = QueueTransport('oci')
    result = queue.status()
    assert not result['configured'] and not result['ready']
    assert result['status'] == 'not_configured'
    factory.assert_not_called()


def test_status_configured_is_not_authenticated_or_live(monkeypatch):
    monkeypatch.setenv('OCI_QUEUE_ID', 'private-queue-id')
    monkeypatch.setenv('OCI_QUEUE_ENDPOINT', 'https://cell.queue.messaging.us-chicago-1.oci.oraclecloud.com')
    monkeypatch.setenv('OCI_AUTH_MODE', 'resource_principal')
    monkeypatch.setattr(module.importlib.util, 'find_spec', lambda name: object())
    queue = QueueTransport('oci')
    result = queue.status()
    assert result['configured'] and not result['ready'] and not result['live_verified']
    assert 'private-queue-id' not in json.dumps(result)


@pytest.mark.parametrize('visibility', [0, 43201, -1, 1.5, True])
def test_visibility_validation(visibility):
    with pytest.raises(ValueError, match='visibility'):
        QueueTransport(visibility=visibility)


@pytest.mark.parametrize('timeout', [-1, 31, 1.5, True])
def test_timeout_validation(timeout):
    with pytest.raises(ValueError, match='timeout'):
        QueueTransport().receive(timeout=timeout)
