import json
import redis.asyncio as redis


class SyncQueue:

    def __init__(self, redis_url: str):

        self.redis = redis.from_url(
            redis_url,
            decode_responses=True,
        )

    async def enqueue(
        self,
        job: dict,
    ):

        await self.redis.rpush(
            "sync_jobs",
            json.dumps(job),
        )

    async def dequeue(self):

        result = await self.redis.blpop(
            "sync_jobs",
            timeout=5,
        )

        if not result:
            return None

        _, payload = result

        return json.loads(payload)
