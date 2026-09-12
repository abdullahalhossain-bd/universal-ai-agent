"""Concurrency benchmark for the public customer message rate limiter.

Usage:
  python scripts/stress_customer_rate_limit.py --url https://api.example.com --api-key TEST --concurrency 100
  python scripts/stress_customer_rate_limit.py --url https://api.example.com --api-key TEST --concurrency 500
  python scripts/stress_customer_rate_limit.py --url https://api.example.com --api-key TEST --concurrency 1000

This intentionally targets a harmless customer GET endpoint. It measures
429 enforcement and client/server failures without creating LLM work.
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="API base URL")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--conversation-id", default="rate-limit-stress")
    parser.add_argument("--concurrency", type=int, choices=(100, 500, 1000), default=100)
    parser.add_argument("--requests", type=int, default=None)
    args = parser.parse_args()

    total = args.requests or args.concurrency
    url = args.url.rstrip("/") + "/v1/messages/customer/" + args.conversation_id
    sem = asyncio.Semaphore(args.concurrency)
    counts: dict[int | str, int] = {}

    async with httpx.AsyncClient(timeout=15.0, limits=httpx.Limits(max_connections=args.concurrency)) as client:
        started = time.perf_counter()

        async def one(i: int) -> None:
            async with sem:
                try:
                    response = await client.get(
                        url,
                        headers={
                            "x-api-key": args.api_key,
                            "x-visitor-id": f"stress-{i}",
                        },
                    )
                    counts[response.status_code] = counts.get(response.status_code, 0) + 1
                except Exception as exc:  # pragma: no cover - benchmark failure path
                    key = type(exc).__name__
                    counts[key] = counts.get(key, 0) + 1

        await asyncio.gather(*(one(i) for i in range(total)))
        elapsed = time.perf_counter() - started

    print(f"requests={total} concurrency={args.concurrency} elapsed={elapsed:.3f}s rps={total / max(elapsed, 0.001):.1f}")
    print("results=" + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))))
    if counts.get(500) or counts.get(502) or counts.get(503):
        raise SystemExit("server-side failures detected")


if __name__ == "__main__":
    asyncio.run(main())
