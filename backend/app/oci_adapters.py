"""OCI SDK adapters. Implemented != configured != live verified.

Clients can be injected for contract tests. Credentials remain server-side and
service exceptions are sanitized before reaching API/job error surfaces.
"""
import base64
import hashlib
import json
import os
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse


class OCIProviderUnavailable(RuntimeError): pass
class OCIServiceFailure(RuntimeError): pass


def _sdk():
    try:
        import oci
        return oci
    except ImportError:
        raise OCIProviderUnavailable('OCI SDK missing; install requirements-oci.txt') from None


def _client(service: str, endpoint: str | None = None, *, region=None, auth_mode=None, profile=None, config_file=None):
    oci = _sdk()
    mode = auth_mode or os.getenv('OCI_AUTH_MODE', 'config_file')
    config = {}
    kwargs = {'timeout': (10, 60), 'retry_strategy': oci.retry.NoneRetryStrategy()}
    try:
        if mode == 'config_file':
            config = oci.config.from_file(config_file or os.getenv('OCI_CONFIG_FILE', '~/.oci/config'), profile or os.getenv('OCI_PROFILE', 'DEFAULT'))
        elif mode == 'instance_principal':
            kwargs['signer'] = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        elif mode == 'resource_principal':
            kwargs['signer'] = oci.auth.signers.get_resource_principals_signer()
        else:
            raise OCIProviderUnavailable('OCI_AUTH_MODE must be config_file, instance_principal or resource_principal')
        selected_region = region or os.getenv('OCI_REGION')
        if selected_region: config['region'] = selected_region
        if endpoint: kwargs['service_endpoint'] = endpoint
        if service == 'storage': return oci.object_storage.ObjectStorageClient(config, **kwargs)
        if service == 'queue': return oci.queue.QueueClient(config, **kwargs)
        raise OCIProviderUnavailable('Unknown OCI service')
    except OCIProviderUnavailable:
        raise
    except Exception:
        raise OCIProviderUnavailable('OCI authentication/client setup failed; verify server-side profile, signer and region') from None


def _safe_call(operation, *args, **kwargs):
    try: return operation(*args, **kwargs)
    except Exception as exc:
        status = getattr(exc, 'status', None)
        if status == 404: raise FileNotFoundError('OCI resource not found or not authorized') from None
        if status in (401,403): raise OCIServiceFailure('OCI authorization failed') from None
        if status == 409: raise OCIServiceFailure('OCI operation conflicted with resource state') from None
        if status == 429: raise OCIServiceFailure('OCI request rate limited; retry later') from None
        raise OCIServiceFailure('OCI service request failed; check connectivity and authorized service diagnostics') from None


def _key(key: str) -> str:
    if not isinstance(key, str) or not key or key.startswith('/') or '\\' in key or any(ord(c)<32 for c in key):
        raise ValueError('Invalid storage key')
    if any(part in ('', '.', '..') for part in key.split('/')): raise ValueError('Invalid storage key')
    if len(key.encode('utf-8')) > 1024: raise ValueError('Storage key too long')
    return key


class OCIStorageAdapter:
    """FileStorage-compatible private Object Storage operations.

    Same logical key always maps to the same object. No bucket creation, public
    URLs, filesystem access or automatic provider fallback occurs.
    """
    def __init__(self, client=None, namespace=None, bucket=None, prefix=None, *, region=None, auth_mode=None, profile=None, config_file=None):
        self.namespace = namespace or os.getenv('OCI_NAMESPACE')
        self.bucket = bucket or os.getenv('OCI_BUCKET')
        self.prefix = os.getenv('OCI_OBJECT_PREFIX', 'aegis') if prefix is None else prefix
        if not self.namespace or not self.bucket: raise OCIProviderUnavailable('OCI_NAMESPACE and OCI_BUCKET are required')
        if self.prefix: _key(self.prefix)
        self.client = client if client is not None else _client('storage', region=region, auth_mode=auth_mode, profile=profile, config_file=config_file)

    def object_key(self, key):
        logical = _key(key)
        return _key(f'{self.prefix}/{logical}' if self.prefix else logical)

    def put(self, key, data):
        if not isinstance(data, bytes): raise TypeError('Storage data must be bytes')
        _safe_call(self.client.put_object, self.namespace, self.bucket, self.object_key(key), data,
            content_length=len(data), content_type='application/octet-stream',
            content_md5=base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode(),
            opc_meta={'sha256': hashlib.sha256(data).hexdigest()})

    def get(self, key):
        response = _safe_call(self.client.get_object, self.namespace, self.bucket, self.object_key(key))
        try:
            data = response.data.content
            digest = response.headers.get('opc-meta-sha256')
            if digest and hashlib.sha256(data).hexdigest() != digest: raise OCIServiceFailure('OCI object checksum mismatch')
            return data
        except OCIServiceFailure:
            raise
        except Exception:
            raise OCIServiceFailure('OCI object response could not be read') from None
        finally:
            close = getattr(response.data, 'close', None)
            if close:
                try: close()
                except Exception: pass

    def json(self, key): return json.loads(self.get(key))
    def put_json(self, key, data): self.put(key, json.dumps(data, ensure_ascii=False).encode())
    def delete(self, key):
        try: _safe_call(self.client.delete_object, self.namespace, self.bucket, self.object_key(key))
        except FileNotFoundError: pass  # Idempotent, same semantics as local unlink(missing_ok=True).

    def test_connection(self):
        """Read-only bucket reachability check; does not prove put/delete rights."""
        _safe_call(self.client.head_bucket, self.namespace, self.bucket)
        return {'ok': True, 'scope': 'bucket_read', 'write_verified': False}


class OCIQueueAdapter:
    """Queue transport seam; jobs and idempotency remain in the database."""
    def __init__(self, client=None, queue_id=None, endpoint=None, models=None):
        self.queue_id = queue_id or os.getenv('OCI_QUEUE_ID')
        endpoint = endpoint or os.getenv('OCI_QUEUE_ENDPOINT')
        if not self.queue_id: raise OCIProviderUnavailable('OCI_QUEUE_ID is required')
        if client is None:
            host = urlparse(endpoint or '')
            if host.scheme != 'https' or not host.hostname or not host.hostname.endswith('.oraclecloud.com') or host.username or host.password:
                raise OCIProviderUnavailable('OCI_QUEUE_ENDPOINT must be the HTTPS OCI messages endpoint')
        self.client = client if client is not None else _client('queue', endpoint)
        self.models = models if models is not None else _sdk().queue.models

    def enqueue(self, job_id):
        if not isinstance(job_id, str) or not job_id or len(job_id)>128: raise ValueError('Invalid job ID')
        payload = self.models.PutMessagesDetails(messages=[self.models.PutMessagesDetailsEntry(content=json.dumps({'job_id':job_id}))])
        result = _safe_call(self.client.put_messages, self.queue_id, payload)
        return [m.id for m in result.data.messages]

    def dequeue(self, limit=1, visibility=900, timeout=20):
        if not 1<=limit<=20 or not 1<=visibility<=43200 or not 0<=timeout<=30: raise ValueError('Invalid queue receive options')
        result = _safe_call(self.client.get_messages, self.queue_id, limit=limit, visibility_in_seconds=visibility, timeout_in_seconds=timeout)
        return [{'receipt':m.receipt, 'content':m.content, 'id':m.id, 'delivery_count':m.delivery_count} for m in result.data.messages]

    def ack(self, receipt):
        if not receipt: raise ValueError('Missing queue receipt')
        _safe_call(self.client.delete_message, self.queue_id, receipt)

    def extend(self, receipt, visibility=900):
        if not receipt or not 0<=visibility<=43200: raise ValueError('Invalid queue lease')
        details = self.models.UpdateMessageDetails(visibility_in_seconds=visibility)
        _safe_call(self.client.update_message, self.queue_id, receipt, details)

    def test_connection(self):
        _safe_call(self.client.get_stats, self.queue_id)
        return {'ok': True, 'scope': 'queue_stats', 'publish_verified': False}


OCI_CAPABILITIES = {
    'object_storage': {'implemented':True,'ready':False,'status':'unverified','reason':'SDK adapter implemented; tenancy connectivity and round-trip not live verified.'},
    'queue': {'implemented':True,'ready':False,'status':'unverified','reason':'SDK transport and durable-job worker integration implemented; live tenancy verification remains outstanding.'},
    'generative_ai': {'implemented':True,'ready':False,'status':'unverified','reason':'OCI Responses adapter implemented in oci_models; tenancy/model round-trip not live verified.'},
    'enterprise_ai_vector_store': {'implemented':True,'ready':False,'status':'unverified','reason':'OCI managed vector-store adapter implemented in oci_models; live ingestion/search not verified.'},
    'managed_postgresql': {'implemented':True,'ready':False,'status':'unverified','reason':'Generic PostgreSQL path exists; OCI TLS, failover and restore not live verified.'},
    'oke': {'implemented':False,'ready':False,'status':'unvalidated','reason':'OKE deployment and workload identity have not been validated.'},
}


def capability_report(): return deepcopy(OCI_CAPABILITIES)


def require_oci_capability(name):
    capability = OCI_CAPABILITIES.get(name)
    if not capability or not capability['implemented']:
        raise OCIProviderUnavailable(capability['reason'] if capability else 'Unknown OCI capability')


def main():
    """Explicit, read-only deployment diagnostic: python -m app.oci_adapters storage."""
    import argparse
    parser = argparse.ArgumentParser(description='Read-only OCI adapter connectivity probes')
    parser.add_argument('service', choices=['storage', 'queue'])
    args = parser.parse_args()
    try:
        adapter = OCIStorageAdapter() if args.service == 'storage' else OCIQueueAdapter()
        print(json.dumps(adapter.test_connection()))
    except (OCIProviderUnavailable, OCIServiceFailure, FileNotFoundError, ValueError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
