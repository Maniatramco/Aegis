"""Durable DB + OCI notification integration, with an in-process fake queue."""

from contextlib import nullcontext
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.queue_transport import QueueTransport


@pytest.fixture
def harness(monkeypatch, tmp_path):
    from app import core, main, queue_transport, worker

    engine = create_engine('sqlite:///' + str(tmp_path / 'queue.db'), connect_args={'check_same_thread': False})
    core.Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, 'Session', session)
    monkeypatch.setattr(main, 'Session', session)
    monkeypatch.setattr(worker, 'document_lock', lambda target: nullcontext())
    monkeypatch.setattr(worker, 'settings', lambda: {'queue_provider': 'oci'})
    monkeypatch.setattr(main, 'settings', lambda: {'queue_provider': 'oci'})
    monkeypatch.setattr(worker, '_last_reconcile', time.monotonic())
    monkeypatch.setattr(main, 'store', Mock())
    client = Mock()
    client.enqueue.return_value = ['message-1']
    client.dequeue.return_value = []
    queue = QueueTransport('oci', adapter=client)
    monkeypatch.setattr(queue_transport, 'get_transport', lambda provider=None: queue)
    processed = []

    def finish(job_id, token):
        processed.append(job_id)
        with session.begin() as db:
            job = db.get(core.Job, job_id)
            assert job.status == 'running' and job.lease_token == token
            job.status = 'completed'
            job.lease_until = 0

    monkeypatch.setattr(worker, 'process', finish)

    def add(job_id, status='queued', attempts=0, lease_until=0, created_at=1):
        with session.begin() as db:
            db.add(core.Record(id='doc-' + job_id, owner='owner', kind='document', name='test.txt', status='queued'))
            db.add(core.Job(id=job_id, owner='owner', target_id='doc-' + job_id,
                            kind='index', status=status, attempts=attempts,
                            lease_until=lease_until, created_at=created_at))

    def notify(job_id):
        client.dequeue.return_value = [{'content': json.dumps({'job_id': job_id}),
                                       'receipt': 'receipt-' + job_id, 'id': 'message-' + job_id,
                                       'delivery_count': 1}]

    result = SimpleNamespace(core=core, main=main, worker=worker, session=session,
                             client=client, queue=queue, processed=processed, add=add, notify=notify)
    yield result
    engine.dispose()


def state(harness, job_id):
    with harness.session() as db:
        return db.get(harness.core.Job, job_id).status


def test_enqueue_commits_database_before_best_effort_publish(harness):
    h = harness

    def publish(job_id):
        # A separate transaction must see the durable row before sending.
        with h.session() as db:
            assert db.get(h.core.Job, job_id).status == 'queued'
        raise RuntimeError('simulated queue outage')

    h.client.enqueue.side_effect = publish
    job = h.main.enqueue('owner', 'index', 'doc-id')
    assert state(h, job.id) == 'queued'
    h.client.enqueue.assert_called_once_with(job.id)
    assert h.main.store.put_json.call_args.args[0] == 'jobs/' + job.id + '.json'


def test_notification_claims_matching_job_then_acknowledges_completion(harness):
    h = harness
    h.add('job-1')
    h.notify('job-1')
    assert h.worker.run_once()
    assert h.processed == ['job-1']
    assert state(h, 'job-1') == 'completed'
    h.client.ack.assert_called_once_with('receipt-job-1')


def test_notified_target_claimed_ahead_of_backlog_between_reconciliation(harness):
    h = harness
    h.add('old-unnotified', created_at=1)
    h.add('new-notified', created_at=2)
    h.notify('new-notified')
    assert h.worker.run_once()
    assert h.processed == ['new-notified']
    assert state(h, 'old-unnotified') == 'queued'


def test_busy_oci_traffic_cannot_starve_lost_notification_job(harness, monkeypatch):
    h = harness
    h.add('old-unnotified', created_at=1)
    h.add('new-notified', created_at=2)
    h.notify('new-notified')
    # A due periodic reconciliation processes the oldest durable job without
    # consuming or hiding a different queued notification.
    monkeypatch.setattr(h.worker, '_last_reconcile', time.monotonic() - 31)
    assert h.worker.run_once()
    assert h.processed == ['old-unnotified']
    h.client.dequeue.assert_not_called()
    h.client.ack.assert_not_called()
    assert h.worker.run_once()
    assert h.processed == ['old-unnotified', 'new-notified']
    h.client.ack.assert_called_once_with('receipt-new-notified')


def test_retry_commits_queued_state_before_notification(harness):
    h = harness
    h.add('retry-me', status='failed', attempts=3)

    def publish(job_id):
        assert state(h, job_id) == 'queued'
        return ['message-retry']

    h.client.enqueue.side_effect = publish
    result = h.main.retry_job('retry-me', owner='owner')
    assert result['status'] == 'queued' and result['attempts'] == 0
    h.client.enqueue.assert_called_once_with('retry-me')


@pytest.mark.parametrize('cause', ['empty', 'outage', 'malformed', 'unknown', 'running'])
def test_database_reconciliation_survives_missing_or_unclaimable_notifications(harness, cause):
    h = harness
    h.add('unnotified')
    if cause == 'outage':
        h.client.dequeue.side_effect = RuntimeError('queue unavailable')
    elif cause == 'malformed':
        h.client.dequeue.return_value = [{'content': 'invalid JSON', 'receipt': 'bad-message'}]
    elif cause == 'unknown':
        h.notify('does-not-exist')
    elif cause == 'running':
        h.add('other-worker', status='running', lease_until=time.time() + 900)
        h.notify('other-worker')
    assert h.worker.run_once()
    assert h.processed == ['unnotified']
    assert state(h, 'unnotified') == 'completed'
    h.client.ack.assert_not_called()


@pytest.mark.parametrize('terminal', ['completed', 'failed', 'cancelled'])
def test_terminal_duplicate_is_acknowledged_without_reprocessing(harness, terminal):
    h = harness
    h.add('duplicate', status=terminal)
    h.notify('duplicate')
    assert h.worker.run_once() is False
    assert h.processed == []
    assert state(h, 'duplicate') == terminal
    h.client.ack.assert_called_once_with('receipt-duplicate')


def test_processing_failure_becomes_durable_terminal_before_ack(harness, monkeypatch):
    h = harness
    h.add('failure')
    h.notify('failure')

    def fail(job_id, token):
        raise ValueError('Invalid input')

    def ack(receipt):
        assert state(h, 'failure') == 'failed'

    monkeypatch.setattr(h.worker, 'process', fail)
    h.client.ack.side_effect = ack
    assert h.worker.run_once()
    h.client.ack.assert_called_once_with('receipt-failure')


def test_lost_database_lease_does_not_ack(harness, monkeypatch):
    h = harness
    h.add('lease-lost')
    h.notify('lease-lost')

    def lost(job_id, token):
        with h.session.begin() as db:
            db.get(h.core.Job, job_id).lease_token = 'other-worker'
        raise InterruptedError('Lease changed')

    monkeypatch.setattr(h.worker, 'process', lost)
    assert h.worker.run_once()
    assert state(h, 'lease-lost') == 'running'
    h.client.ack.assert_not_called()


def test_cancellation_is_terminal_and_acknowledged(harness, monkeypatch):
    h = harness
    h.add('cancelled')
    h.notify('cancelled')

    def cancel(job_id, token):
        with h.session.begin() as db:
            db.get(h.core.Job, job_id).status = 'cancelled'
        raise InterruptedError('Cancelled')

    monkeypatch.setattr(h.worker, 'process', cancel)
    assert h.worker.run_once()
    h.client.ack.assert_called_once_with('receipt-cancelled')


def test_exhausted_stale_job_is_failed_then_notification_acknowledged(harness):
    h = harness
    h.add('exhausted', status='running', attempts=3, lease_until=1)
    h.notify('exhausted')
    assert not h.worker.run_once()
    assert state(h, 'exhausted') == 'failed'
    h.client.ack.assert_called_once_with('receipt-exhausted')


def test_queue_ack_failure_does_not_roll_back_completed_job(harness):
    h = harness
    h.add('job-1')
    h.notify('job-1')
    h.client.ack.side_effect = RuntimeError('queue ack failed')
    assert h.worker.run_once()
    assert state(h, 'job-1') == 'completed'
    # Redelivery can retry the ack but cannot execute a terminal job again.
    h.client.ack.side_effect = None
    assert not h.worker.run_once()
    assert h.processed == ['job-1']
    assert h.client.ack.call_count == 2


def test_heartbeat_renews_queue_receipt_while_database_lease_is_held(harness, monkeypatch):
    h = harness
    h.add('job-1')
    h.notify('job-1')

    class OneHeartbeat:
        calls = 0

        def wait(self, seconds):
            self.calls += 1
            return self.calls > 1

        def set(self):
            pass

    class InlineThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout):
            pass

    def extend(receipt, visibility):
        with h.session() as db:
            job = db.get(h.core.Job, 'job-1')
            assert job.status == 'running'
            assert job.lease_until > time.time() + 850

    h.client.extend.side_effect = extend
    monkeypatch.setattr(h.worker, 'threading', SimpleNamespace(Event=OneHeartbeat, Thread=InlineThread))
    assert h.worker.run_once()
    h.client.extend.assert_called_once_with('receipt-job-1', visibility=900)
