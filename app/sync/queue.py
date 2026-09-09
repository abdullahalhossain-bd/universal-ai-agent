"""Durable Redis Streams queue for product sync jobs."""
from __future__ import annotations
import json, logging, time, uuid
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
        key = f"{STREAM}:delayed"
        items = await self.redis.zrangebyscore(key, 0, time.time(), start=0, num=limit)
        for raw in items:
            try:
                await self.redis.xadd(STREAM, json.loads(raw))
                await self.redis.zrem(key, raw)
            except Exception:
                logger.exception("failed promoting delayed sync job")

    async def acquire_lock(self, datasource_id, token):
        return bool(await self.redis.set(f"sync_lock:{datasource_id}", token, nx=True, px=LOCK_TTL_MS))

    async def renew_lock(self, datasource_id, token):
        script = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('pexpire',KEYS[1],ARGV[2]) else return 0 end"
        return bool(await self.redis.eval(script, 1, f"sync_lock:{datasource_id}", token, LOCK_TTL_MS))

    async def release_lock(self, datasource_id, token):
        script = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
        await self.redis.eval(script, 1, f"sync_lock:{datasource_id}", token)

    async def claim_stale(self, consumer, count=10):
        await self._ensure_group()
        try:
            r = await self.redis.xautoclaim(
                STREAM, GROUP, consumer, min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=count
            )
        except (redis.ResponseError, AttributeError):
            return []
        return self._decode_entries(r[1] if len(r) > 1 else [])

    async def read(self, consumer, count=1, block_ms=5000):
        await self._ensure_group()
        r = await self.redis.xreadgroup(
            GROUP, consumer, streams={STREAM: ">"}, count=count, block=block_ms
        )
        return self._decode_entries(r[0][1]) if r else []

    async def ack(self, message_id):
        await self.redis.xack(STREAM, GROUP, message_id)

    async def requeue_or_dlq(self, message_id, job, attempt, error):
        attempt = int(attempt)
        group_id = str(job.get("_retry_group_id") or uuid.uuid4())
        base_job = dict(job)
        base_job["_retry_group_id"] = group_id
        base_job["_retry_attempt"] = attempt
        if attempt >= MAX_ATTEMPTS:
            await self.redis.xadd(
                DLQ_STREAM,
                {
                    "job": json.dumps(base_job, separators=(",", ":"), sort_keys=True),
                    "attempt": str(attempt),
                    "error": str(error)[:4000],
                    "source_message_id": message_id,
                    "retry_group_id": group_id,
                },
            )
            await self.ack(message_id)
            return "dead_letter"
        payload = json.dumps(base_job, separators=(",", ":"), sort_keys=True)
        delayed_entry = {
            "job": payload,
            "job_id": str(uuid.uuid4()),
            "attempt": str(attempt),
            "retry_group_id": group_id,
        }
        raw = json.dumps(delayed_entry, separators=(",", ":"), sort_keys=True)
        await self.redis.zadd(f"{STREAM}:delayed", {raw: time.time() + retry_delay(attempt)})
        await self.ack(message_id)
        return "retry"

    @staticmethod
    def _decode_entries(entries):
        out = []
        for message_id, fields in entries:
            try:
                payload = json.loads(fields["job"])
                if not isinstance(payload, dict):
                    continue
                attempt = int(fields.get("attempt", payload.get("_retry_attempt", 0)))
                payload["_retry_attempt"] = attempt
                out.append((message_id, payload, attempt))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                logger.exception("Invalid sync queue message %s", message_id)
        return out
