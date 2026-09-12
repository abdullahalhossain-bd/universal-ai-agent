import json

import pytest

from app.sync.dlq import (
    KNOWN_FIXED_PAGINATION_ERROR,
    SyncDLQManager,
    classify_dlq_error,
)


class FakeRedis:
    def __init__(self):
        self.dlq = {}
        self.stream = []

    async def xrevrange(self, name, max="+", min="-", count=50):
        rows = list(self.dlq.items())[::-1]
        if max.startswith("("):
            rows = [(k, v) for k, v in rows if k < max[1:]]
        return rows[:count]

    async def xrange(self, name, min="-", max="+", count=1):
        return [(k, v) for k, v in self.dlq.items() if k == min][:count]

    async def eval(self, script, numkeys, dlq, stream, message_id, raw_job, retry_group_id, job_id):
        if message_id not in self.dlq:
            return ""
        self.stream.append({
            "job": raw_job,
            "job_id": job_id,
            "attempt": "0",
            "retry_group_id": retry_group_id,
        })
        del self.dlq[message_id]
        return f"{len(self.stream)}-0"


@pytest.mark.asyncio
async def test_dlq_classification_is_specific_and_non_destructive():
    assert classify_dlq_error(KNOWN_FIXED_PAGINATION_ERROR) == "known_fixed_pagination_bug"
    assert classify_dlq_error("malformed queue message: bad json") == "malformed_queue_message"
    assert classify_dlq_error("HTTP 500 from datasource") == "unknown"


@pytest.mark.asyncio
async def test_replay_only_known_fixed_bug_and_removes_after_atomic_move():
    redis = FakeRedis()
    redis.dlq = {
        "10-0": {
            "job": json.dumps({"datasource_id": "ds-1", "job_type": "sync", "_retry_group_id": "g1"}),
            "attempt": "3",
            "error": KNOWN_FIXED_PAGINATION_ERROR,
            "source_message_id": "9-0",
            "retry_group_id": "g1",
        },
        "11-0": {
            "job": json.dumps({"datasource_id": "ds-2"}),
            "attempt": "3",
            "error": "HTTP 500 from datasource",
            "source_message_id": "8-0",
            "retry_group_id": "g2",
        },
    }
    manager = SyncDLQManager(redis)

    result = await manager.replay_known_fixed(["10-0", "11-0"])

    assert [item["id"] for item in result["replayed"]] == ["10-0"]
    assert {item["id"] for item in result["skipped"]} == {"11-0"}
    assert "10-0" not in redis.dlq
    assert "11-0" in redis.dlq
    assert len(redis.stream) == 1
    replayed_job = json.loads(redis.stream[0]["job"])
    assert replayed_job["_retry_attempt"] == 0


@pytest.mark.asyncio
async def test_inspect_paginates_without_mutating_dlq():
    redis = FakeRedis()
    for i in range(3):
        redis.dlq[f"{i + 1}-0"] = {
            "job": json.dumps({"datasource_id": f"ds-{i}"}),
            "attempt": "3",
            "error": KNOWN_FIXED_PAGINATION_ERROR,
            "source_message_id": f"{i}-0",
            "retry_group_id": f"g-{i}",
        }
    manager = SyncDLQManager(redis)

    first = await manager.inspect(limit=2)
    second = await manager.inspect(limit=2, cursor=first["next_cursor"])

    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert len(redis.dlq) == 3
