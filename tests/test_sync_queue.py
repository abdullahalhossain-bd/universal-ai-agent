import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.sync.queue import GROUP, SyncQueue
from app.sync.worker import _describe_lock_renewal_error, _lock_renewal_interval


class FakeRedis:
    def __init__(self):
        self.evals = []

    async def eval(self, script, numkeys, *args):
        self.evals.append((script, numkeys, args))
        return 1


@pytest.mark.asyncio
async def test_decode_preserves_retry_group_id_from_stream_metadata():
    queue = SyncQueue.__new__(SyncQueue)
    queue.redis = FakeRedis()

    entries = await queue._decode_entries([
        ("1-0", {"job": json.dumps({"datasource_id": "ds-1"}), "attempt": "2", "retry_group_id": "group-1"})
    ])

    assert entries[0][1]["_retry_attempt"] == 2
    assert entries[0][1]["_retry_group_id"] == "group-1"


@pytest.mark.asyncio
async def test_retry_ack_and_delayed_write_use_one_atomic_script():
    queue = SyncQueue.__new__(SyncQueue)
    queue.redis = FakeRedis()

    outcome = await queue.requeue_or_dlq("1-0", {"datasource_id": "ds-1", "_retry_group_id": "group-1"}, 1, "temporary")

    assert outcome == "retry"
    assert len(queue.redis.evals) == 1
    script, key_count, args = queue.redis.evals[0]
    assert key_count == 2
    assert "zadd" in script and "xack" in script
    assert args[-2:] == (GROUP, "1-0")


@pytest.mark.asyncio
async def test_dlq_ack_and_write_use_one_atomic_script():
    queue = SyncQueue.__new__(SyncQueue)
    queue.redis = FakeRedis()

    outcome = await queue.requeue_or_dlq("1-0", {"datasource_id": "ds-1", "_retry_group_id": "group-1"}, 999, "permanent")

    assert outcome == "dead_letter"
    assert len(queue.redis.evals) == 1
    script, key_count, args = queue.redis.evals[0]
    assert key_count == 2
    assert "xadd" in script and "xack" in script
    assert args[-2:] == ("group-1", GROUP)


@pytest.mark.asyncio
async def test_malformed_message_keeps_raw_job_in_dlq_script():
    queue = SyncQueue.__new__(SyncQueue)
    queue.redis = FakeRedis()

    await queue._decode_entries([("1-0", {"job": "not-json", "attempt": "0"})])

    _, _, args = queue.redis.evals[0]
    assert args[2] == "not-json"


@pytest.mark.asyncio
async def test_worker_stats_logging_is_best_effort_for_redis_failures():
    from app.sync.worker import _log_queue_stats

    class FailingQueue:
        async def stats(self):
            raise ConnectionError("xpending temporarily failed")

    await _log_queue_stats(FailingQueue(), "worker-1")

    class HealthyQueue:
        async def stats(self):
            return {"stream_length": 1, "pending": 0, "delayed": 0, "dead_letter": 0}

    await _log_queue_stats(HealthyQueue(), "worker-2")


def test_lock_renewal_interval_scales_for_short_ttl():
    assert _lock_renewal_interval(5000) == 1.0
    assert _lock_renewal_interval(600_000) == 30.0


def test_lock_renewal_error_details_include_exception_type_and_message():
    assert _describe_lock_renewal_error(TimeoutError("read timed out")) == "TimeoutError: read timed out"
    assert _describe_lock_renewal_error(ConnectionError("socket closed")) == "ConnectionError: socket closed"