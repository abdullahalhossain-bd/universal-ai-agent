import asyncio

from app.sync.scheduler import get_active_datasources
from app.sync.queue import SyncQueue


async def main():
    datasources = await get_active_datasources()

    if not datasources:
        print("NO ACTIVE DATASOURCES")
        return

    ds = datasources[0]

    job = {
        "store_id": ds["store_id"],
        "datasource_id": ds["id"],
        "job_type": "product_sync",
        "full_sync": ds["full_sync"],
    }

    queue = SyncQueue("redis://localhost:6379")
    await queue.enqueue(job)

    print("ENQUEUED:")
    print(job)

    await queue.redis.aclose()


asyncio.run(main())
