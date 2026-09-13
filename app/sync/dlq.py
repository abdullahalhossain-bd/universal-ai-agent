"""Safe inspection and replay helpers for the sync dead-letter queue."""
from __future__ import annotations

import json
from typing import Any

from app.sync.queue import DLQ_STREAM, STREAM

KNOWN_FIXED_PAGINATION_ERROR = "Query.filter() being called on a Query which already has LIMIT or OFFSET applied."


def classify_dlq_error(error: str) -> str:
    text = str(error or "")
    if KNOWN_FIXED_PAGINATION_ERROR in text or (
        "Query.filter()" in text and "LIMIT or OFFSET" in text
    ):
        return "known_fixed_pagination_bug"
    if "malformed queue message" in text:
        return "malformed_queue_message"
    return "unknown"


def decode_dlq_entry(message_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    error = str(fields.get("error", ""))
    raw_job = str(fields.get("job", ""))
    job: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw_job)
        if isinstance(parsed, dict):
            job = parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        job = None
    return {
        "id": message_id,
        "attempt": int(fields.get("attempt", 0) or 0),
        "error": error,
        "classification": classify_dlq_error(error),
        "retry_group_id": str(fields.get("retry_group_id", "")),
        "source_message_id": str(fields.get("source_message_id", "")),
        "job": job,
    }


class SyncDLQManager:
    def __init__(self, redis):
        self.redis = redis

    async def inspect(self, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        maximum = f"({cursor}" if cursor else "+"
        entries = await self.redis.xrevrange(DLQ_STREAM, max=maximum, min="-", count=limit)
        items = [decode_dlq_entry(message_id, fields) for message_id, fields in entries]
        next_cursor = items[-1]["id"] if len(items) == limit else None
        return {"items": items, "next_cursor": next_cursor}

    async def replay_known_fixed(self, message_ids: list[str]) -> dict[str, Any]:
        if not message_ids:
            return {"replayed": [], "skipped": []}
        if len(message_ids) > 50:
            raise ValueError("At most 50 DLQ messages can be replayed per request")

        replayed: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        for message_id in message_ids:
            rows = await self.redis.xrange(DLQ_STREAM, min=message_id, max=message_id, count=1)
            if not rows:
                skipped.append({"id": message_id, "reason": "not_found_or_already_replayed"})
                continue
            _, fields = rows[0]
            item = decode_dlq_entry(message_id, fields)
            if item["classification"] != "known_fixed_pagination_bug":
                skipped.append({"id": message_id, "reason": item["classification"]})
                continue
            if not isinstance(item["job"], dict) or not item["job"].get("datasource_id"):
                skipped.append({"id": message_id, "reason": "missing_datasource_id"})
                continue

            job = dict(item["job"])
            job["_retry_attempt"] = 0
            raw_job = json.dumps(job, separators=(",", ":"), sort_keys=True)
            script = """
            local rows = redis.call('xrange', KEYS[1], ARGV[1], ARGV[1], 'COUNT', 1)
            if #rows == 0 then return '' end
            local job = ARGV[2]
            local retry_group_id = ARGV[3]
            local new_id = redis.call('xadd', KEYS[2], '*',
                'job', job,
                'job_id', ARGV[4],
                'attempt', '0',
                'retry_group_id', retry_group_id)
            redis.call('xdel', KEYS[1], ARGV[1])
            return new_id
            """
            new_id = await self.redis.eval(
                script,
                2,
                DLQ_STREAM,
                STREAM,
                message_id,
                raw_job,
                item["retry_group_id"] or str(job.get("_retry_group_id", "")),
                str(job.get("job_id", "")),
            )
            if new_id:
                replayed.append({"id": message_id, "new_message_id": str(new_id)})
            else:
                skipped.append({"id": message_id, "reason": "not_found_or_already_replayed"})
        return {"replayed": replayed, "skipped": skipped}
