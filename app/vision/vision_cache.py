class VisionCache:

    def __init__(self, redis_client):

        self.redis = redis_client

    async def get(
        self,
        image_hash: str,
    ):

        key = f"vision:{image_hash}"

        return await self.redis.get(key)

    async def set(
        self,
        image_hash: str,
        analysis: dict,
        ttl_seconds: int = 86400,
    ):

        import json

        key = f"vision:{image_hash}"

        await self.redis.set(
            key,
            json.dumps(analysis),
            ex=ttl_seconds,
        )
