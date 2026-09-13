import json

import pytest

from app.sync.queue import GROUP, SyncQueue


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