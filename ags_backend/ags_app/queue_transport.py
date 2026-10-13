"""Optional OCI Queue notifications for the durable database job queue.

The Job table is the source of truth. Call ``notify`` only after committing a
job, and ALWAYS reconcile the database in the worker, even when receive returns
no notification or a notification cannot be claimed. Notification failure must
never undo a committed job or prevent database lease recovery.

Receipts are acknowledged only after reading a terminal Job status. A worker
holding the database lease calls ``renew`` during its heartbeat. Duplicate,
expired, malformed and unclaimable notifications do not authorize execution or
acknowledgement; database claim/lease-token checks remain mandatory.
"""

from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import json
import logging
import os
import threading
from urllib.parse import urlparse

from .oci_adapters import OCIProviderUnavailable, OCIQueueAdapter, OCIServiceFailure


logger = logging.getLogger(__name__)
TERMINAL_STATUSES = frozenset({'completed', 'failed', 'cancelled'})
VISIBILITY_SECONDS = 900


@dataclass(frozen=True)
class QueueDelivery:
    job_id: str
    receipt: str
    message_id: str = ''
    delivery_count: int = 0


def _valid_job_id(value):
    return (isinstance(value, str) and 0 < len(value) <= 128
            and value.strip() == value and all(32 < ord(c) < 127 for c in value))


def _environment_configured():
    """A syntax check only. Never read a credential file or initialize a signer."""
    try:
        endpoint = urlparse(os.getenv('OCI_QUEUE_ENDPOINT', ''))
        valid_endpoint = (endpoint.scheme == 'https' and endpoint.hostname
                          and endpoint.hostname.endswith('.oraclecloud.com')
                          and not endpoint.username and not endpoint.password)
    except ValueError:
        valid_endpoint = False
    return bool(os.getenv('OCI_QUEUE_ID') and valid_endpoint
                and os.getenv('OCI_AUTH_MODE', 'config_file') in
                ('config_file', 'instance_principal', 'resource_principal'))


class QueueTransport:
    """Best-effort transport over OCIQueueAdapter; never a second job database.

    Inject an adapter for credential-free contract tests. The default database
    provider never imports the OCI SDK, initializes credentials, or makes calls.
    ``ready`` for OCI requires publish, receive, and terminal ack observed in this
    process. A read-only connection probe alone cannot certify that round trip.
    """

    def __init__(self, provider='database', *, adapter=None, visibility=VISIBILITY_SECONDS):
        if provider not in ('database', 'oci'):
            raise ValueError('QUEUE_PROVIDER must be database or oci')
        if not isinstance(visibility, int) or isinstance(visibility, bool) or not 1 <= visibility <= 43200:
            raise ValueError('Invalid queue visibility duration')
        if provider == 'database' and adapter is not None:
            raise ValueError('The database queue provider does not use an OCI adapter')
        self.provider = provider
        self.visibility = visibility
        self._adapter = adapter
        self._injected = adapter is not None
        self._lock = threading.RLock()
        self._verified = {'publish': False, 'receive': False, 'acknowledgement': False, 'lease_renewal': False, 'connection': False}
        self._errors = {}
        self._published_jobs = set()
        self._round_trip_receipts = set()
        self._round_trip_observed = False

    def _oci(self):
        with self._lock:
            if self._adapter is None:
                self._adapter = OCIQueueAdapter()
            return self._adapter

    def _success(self, operation):
        with self._lock:
            self._verified[operation] = True
            self._errors.pop(operation, None)

    def _failure(self, operation):
        # No exception text, content, destination, receipt, signer or credentials
        # can appear in logs, readiness responses or job errors.
        message = f'OCI Queue {operation.replace("_", " ")} failed; database reconciliation remains available'
        with self._lock:
            changed = self._errors.get(operation) != message
            self._errors[operation] = message
        if changed:
            logger.warning(message)

    def notify(self, job_id):
        """Publish an identifier after DB commit; False still leaves a valid job."""
        if not _valid_job_id(job_id):
            raise ValueError('Invalid job ID')
        if self.provider == 'database':
            return True
        try:
            message_ids = self._oci().enqueue(job_id)
            if not message_ids:
                raise OCIServiceFailure('Queue publish returned no message identifier')
            with self._lock:
                if len(self._published_jobs) >= 4096:
                    self._published_jobs.pop()
                self._published_jobs.add(job_id)
            self._success('publish')
            return True
        except Exception:
            self._failure('publish')
            return False

    def receive(self, timeout=0):
        """Receive one notification, without claiming or changing any DB job.

        Nonblocking by default so database reconciliation cannot be delayed by
        an empty OCI queue. Callers may request up to 30 seconds of long polling.
        Invalid payloads are deliberately left unacknowledged for queue retry /
        configured dead-letter handling; they do not block database polling.
        """
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 0 <= timeout <= 30:
            raise ValueError('Invalid queue receive timeout')
        if self.provider == 'database':
            return None
        try:
            messages = self._oci().dequeue(limit=1, visibility=self.visibility, timeout=timeout)
            self._success('connection')
            if not messages:
                with self._lock:
                    self._errors.pop('receive', None)
                return None
            message = messages[0]
            content = message['content']
            if not isinstance(content, str) or len(content) > 4096:
                raise ValueError('Invalid queue notification')
            payload = json.loads(content)
            if not isinstance(payload, dict) or not _valid_job_id(payload.get('job_id')):
                raise ValueError('Invalid queue notification')
            receipt = message['receipt']
            if not isinstance(receipt, str) or not receipt:
                raise ValueError('Invalid queue receipt')
            delivery = QueueDelivery(
                job_id=payload['job_id'], receipt=receipt,
                message_id=str(message.get('id', '')),
                delivery_count=int(message.get('delivery_count', 0)),
            )
            with self._lock:
                if delivery.job_id in self._published_jobs:
                    if len(self._round_trip_receipts) >= 4096:
                        self._round_trip_receipts.pop()
                    self._round_trip_receipts.add((delivery.job_id, delivery.receipt))
            self._success('receive')
            return delivery
        except Exception:
            self._failure('receive')
            return None

    def renew(self, delivery):
        """Extend a received message while the matching database lease is held."""
        if self.provider == 'database' or delivery is None:
            return False
        try:
            self._oci().extend(delivery.receipt, visibility=self.visibility)
            self._success('lease_renewal')
            return True
        except Exception:
            self._failure('lease_renewal')
            return False

    def ack_terminal(self, delivery, status):
        """Ack only a terminal status freshly read from this delivery's DB job.

        Unknown/deleted rows are NOT terminal. Nor are queued/running/retry jobs.
        The caller must look up delivery.job_id rather than a different job it
        happened to claim through reconciliation.
        """
        if self.provider == 'database' or delivery is None or status not in TERMINAL_STATUSES:
            return False
        try:
            self._oci().ack(delivery.receipt)
            with self._lock:
                pair = (delivery.job_id, delivery.receipt)
                if pair in self._round_trip_receipts:
                    self._round_trip_observed = True
                    self._round_trip_receipts.discard(pair)
                    self._published_jobs.discard(delivery.job_id)
            self._success('acknowledgement')
            return True
        except Exception:
            self._failure('acknowledgement')
            return False

    def test_connection(self):
        """Explicit read-only probe. Does not consume a message or publish a job."""
        if self.provider == 'database':
            return {'ok': True, 'provider': 'database', 'scope': 'database_queue_selected', 'database_connectivity_verified': False}
        try:
            result = self._oci().test_connection()
            if not isinstance(result, dict) or result.get('ok') is not True:
                raise OCIServiceFailure('OCI Queue connection probe failed')
            self._success('connection')
            return {'ok': True, 'provider': 'oci', 'scope': 'queue_stats', 'publish_verified': self._verified['publish'], 'live_verified': self._round_trip_verified()}
        except OCIProviderUnavailable:
            self._failure('connection')
            raise OCIProviderUnavailable('OCI Queue is not configured; verify the SDK, queue endpoint, ID and server-side identity') from None
        except Exception:
            self._failure('connection')
            raise OCIServiceFailure('OCI Queue read-only connection probe failed; verify authorized service diagnostics') from None

    def _round_trip_verified(self):
        return self._round_trip_observed

    def status(self, probe=False):
        """Sanitized process-local facts, not a claim that OCI was deployed/tested."""
        if self.provider == 'database':
            return {'provider': 'database', 'implemented': True, 'configured': True,
                    'ready': True, 'status': 'local', 'live_verified': False,
                    'durable_source': 'database', 'reconciliation_required': True,
                    'reason': 'Database polling selected; no external queue required'}
        if probe:
            try:
                self.test_connection()
            except (OCIProviderUnavailable, OCIServiceFailure):
                pass
        with self._lock:
            configured = self._injected or _environment_configured()
            sdk_available = self._injected or importlib.util.find_spec('oci') is not None
            live_verified = self._round_trip_verified()
            ready = bool(configured and sdk_available and live_verified and not self._errors)
            if self._errors:
                state, reason = 'degraded', '; '.join(self._errors.values())
            elif not configured:
                state, reason = 'not_configured', 'OCI_QUEUE_ID, HTTPS OCI_QUEUE_ENDPOINT and supported OCI_AUTH_MODE are required'
            elif not sdk_available:
                state, reason = 'not_configured', 'OCI SDK missing; install requirements-oci.txt'
            elif not live_verified:
                state, reason = 'unverified', 'OCI transport configured; publish/receive/terminal-ack round trip is not verified in this process'
            else:
                state, reason = 'verified', 'Publish, receive and terminal acknowledgement observed in this process'
            return {'provider': 'oci', 'implemented': True, 'configured': configured,
                    'sdk_available': sdk_available, 'ready': ready, 'status': state,
                    'live_verified': live_verified, 'durable_source': 'database',
                    'reconciliation_required': True, 'reason': reason,
                    'checks': self._verified.copy()}


@lru_cache(maxsize=16)
def _transport(provider, environment_signature):
    # Include environment settings in the cache key so tests and explicit
    # process reconfiguration cannot reuse a client for an old queue/identity.
    return QueueTransport(provider)


def get_transport(provider=None):
    """Settings callers pass queue_provider explicitly; standalone use uses env."""
    selected = provider if provider is not None else os.getenv('QUEUE_PROVIDER', 'database')
    signature = tuple(os.getenv(key, '') for key in (
        'OCI_QUEUE_ID', 'OCI_QUEUE_ENDPOINT', 'OCI_AUTH_MODE', 'OCI_CONFIG_FILE',
        'OCI_PROFILE', 'OCI_REGION',
    )) if selected == 'oci' else ()
    return _transport(selected, signature)


def notify_job(job_id, provider=None):
    """Convenience post-commit hook, using the same cached transport as workers."""
    return get_transport(provider).notify(job_id)
