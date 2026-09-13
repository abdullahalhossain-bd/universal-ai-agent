"""Durable Redis Streams queue for product sync jobs.

The queue is deliberately broker-like: jobs are never evicted, retries are
bounded, stale consumers can be reclaimed, malformed messages are dead-lettered,
and delayed retries are promoted atomically so worker crashes cannot silently
duplicate a retry.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import redis.asyncio as redis

from app.sync.retry import MAX_ATTEMPTS, retry_delay

logger = logging.getLogger("app.sync.queue")
STREAM = "sync_jobs"
DLQ_STREAM = "sync_jobs_dlq"
GROUP = "sync_workers"
CLAIM_IDLE_MS = 300_000
LOCK_TTL_MS = 600_000
ENQUEUE_TTL_MS = 7_200_000
DELAYED_KEY = f"{STREAM}:delayed"


class SyncQueue:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def close(self):
        await self.redis.aclose()

    async def _ensure_group(self):
        try:
            await self.redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(self, job: dict[str, Any]):
        await self._ensure_group()
        ds = job.get("datasource_id")
        marker = f"sync_enqueued:{ds}" if ds else None
        if marker and not await self.redis.set(marker, "1", nx=True, ex=ENQUEUE_TTL_MS // 1000):
            return None
        try:
            payload = dict(job)
            payload.setdefault("_retry_group_id", str(uuid.uuid4()))
            payload["_retry_attempt"] = int(payload.get("_retry_attempt", 0))
            raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            return str(await self.redis.xadd(STREAM, {"job": raw, "job_id": str(uuid.uuid4()), "attempt": "0"}))
        except Exception:
            if marker:
                await self.redis.delete(marker)
            raise

    async def clear_enqueue_marker(self, datasource_id: str):
        if datasource_id:
            await self.redis.delete(f"sync_enqueued:{datasource_id}")

    async def promote_delayed(self, limit: int = 100):
        """Atomically move due delayed jobs back to the stream."""
        limit = max(1, min(int(limit), 1000))
        script = """
        local items = redis.call('zrangebyscore', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
        for _, raw in ipairs(items) do
            local payload = cjson.decode(raw)
            redis.call('xadd', ARGV[3], '*',
                'job', tostring(payload['job']),
                'job_id', tostring(payload['job_id']),
                'attempt', tostring(payload['attempt']),
                'retry_group_id', tostring(payload['retry_group_id']))
            redis.call('zrem', KEYS[1], raw)
        end
        return #items
        """
        try:
            return int(await self.redis.eval(script, 1, DELAYED_KEY, time.time(), limit, STREAM))
        except Exception:
            logger.exception("failed promoting delayed sync jobs")
            return 0

    async def acquire_lock(self, datasource_id, token):
        return bool(await self.redis.set(f"sync_lock:{datasource_id}", token, nx=True, px=LOCK_TTL_MS))

    async def renew_lock(self, datasource_id, token):
        script = """
        if redis.call('get',KEYS[1]) == ARGV[1] then
            return redis.call('pexpire',KEYS[1],ARGV[2])
        else
            return 0
        end
        """
        return bool(await self.redis.eval(script, 1, f"sync_lock:{datasource_id}", token, LOCK_TTL_MS))

    async def release_lock(self, datasource_id, token):
        script = """
        if redis.call('get',KEYS[1]) == ARGV[1] then
            return redis.call('del',KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(script, 1, f"sync_lock:{datasource_id}", token)

    async def claim_stale(self, consumer, count=10):
        await self._ensure_group()
        try:
            r = await self.redis.xautoclaim(STREAM, GROUP, consumer, min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=max(1, min(int(count), 100)))
        except (redis.ResponseError, AttributeError):
            return []
        return await self._decode_entries(r[1] if len(r) > 1 else [])

    async def read(self, consumer, count=1, block_ms=5000):
        await self._ensure_group()
        r = await self.redis.xreadgroup(GROUP, consumer, streams={STREAM: ">"}, count=max(1, min(int(count), 100)), block=max(100, int(block_ms)))
        return await self._decode_entries(r[0][1]) if r else []

    async def ack(self, message_id):
        await self.redis.xack(STREAM, GROUP, message_id)

    async def _dead_letter(self, message_id, job, attempt, error, retry_group_id=""):
        script = """
        redis.call('xadd', KEYS[1], '*',
            'job', ARGV[1],
            'attempt', ARGV[2],
            'error', ARGV[3],
            'source_message_id', ARGV[4],
            'retry_group_id', ARGV[5])
        return redis.call('xack', KEYS[2], ARGV[6], ARGV[4])
        """
        raw_job = job if isinstance(job, str) else json.dumps(job, separators=(",", ":"), sort_keys=True)
        return await self.redis.eval(
            script,
            2,
            DLQ_STREAM,
            STREAM,
            raw_job,
            str(attempt),
            str(error)[:4000],
            message_id,
            str(retry_group_id),
            GROUP,
        )

    async def requeue_or_dlq(self, message_id, job, attempt, error):
        attempt = int(attempt)
        group_id = str(job.get("_retry_group_id") or uuid.uuid4())
        base_job = dict(job)
        base_job["_retry_group_id"] = group_id
        base_job["_retry_attempt"] = attempt
        if attempt >= MAX_ATTEMPTS:
            await self._dead_letter(message_id, base_job, attempt, error, group_id)
            return "dead_letter"
        delayed_entry = {
            "job": json.dumps(base_job, separators=(",", ":"), sort_keys=True),
            "job_id": str(uuid.uuid4()),
            "attempt": str(attempt),
            "retry_group_id": group_id,
        }
        raw = json.dumps(delayed_entry, separators=(",", ":"), sort_keys=True)
        script = """
        redis.call('zadd', KEYS[1], ARGV[1], ARGV[2])
        return redis.call('xack', KEYS[2], ARGV[3], ARGV[4])
        """
        await self.redis.eval(
            script,
            2,
            DELAYED_KEY,
            STREAM,
            time.time() + retry_delay(attempt),
            raw,
            GROUP,
            message_id,
        )
        return "retry"

    async def defer_message(self, message_id, job, attempt, delay: float = 1.0):
        payload = dict(job)
        payload["_retry_attempt"] = int(attempt)
        delayed_entry = {
            "job": json.dumps(payload, separators=(",", ":"), sort_keys=True),
            "job_id": str(uuid.uuid4()),
            "attempt": str(attempt),
            "retry_group_id": str(payload.get("_retry_group_id") or uuid.uuid4()),
        }
        raw = json.dumps(delayed_entry, separators=(",", ":"), sort_keys=True)
        script = """
        redis.call('zadd', KEYS[1], ARGV[1], ARGV[2])
        return redis.call('xack', KEYS[2], ARGV[3], ARGV[4])
        """
        await self.redis.eval(
            script,
            2,
            DELAYED_KEY,
            STREAM,
            time.time() + max(0.25, float(delay)),
            raw,
            GROUP,
            message_id,
        )

    async def stats(self) -> dict[str, int]:
        try:
            pending = await self.redis.xpending(STREAM, GROUP)
            return {
                "stream_length": int(await self.redis.xlen(STREAM)),
                "pending": int(pending.get("pending", 0)) if isinstance(pending, dict) else 0,
                "delayed": int(await self.redis.zcard(DELAYED_KEY)),
                "dead_letter": int(await self.redis.xlen(DLQ_STREAM)),
            }
        except Exception:
            logger.exception("failed reading sync queue stats")
            return {"stream_length": -1, "pending": -1, "delayed": -1, "dead_letter": -1}

    async def _decode_entries(self, entries):
        out = []
        for message_id, fields in entries:
            try:
                payload = json.loads(fields["job"])
                if not isinstance(payload, dict):
                    raise ValueError("job payload is not an object")
                attempt = int(fields.get("attempt", payload.get("_retry_attempt", 0)))
                payload["_retry_attempt"] = attempt
                if fields.get("retry_group_id"):
                    payload["_retry_group_id"] = fields["retry_group_id"]
                out.append((message_id, payload, attempt))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.error("Dead-lettering malformed sync queue message=%s error=%s", message_id, exc)
                await self._dead_letter(
                    message_id,
                    str(fields.get("job", ""))[:10000],
                    fields.get("attempt", "0"),
                    f"malformed queue message: {exc}",
                    fields.get("retry_group_id", ""),
                )
        return out
