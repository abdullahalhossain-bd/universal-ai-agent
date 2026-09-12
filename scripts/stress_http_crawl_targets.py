"""Concurrent HTTP target harness for crawler/load testing.

The harness is deliberately target-agnostic: point it at a controlled test
server that serves representative ecommerce pages. It never generates random
internet traffic. Use --count 100/500/1000 to exercise queue/concurrency and
failure accounting in a staging environment.

Example:
  python scripts/stress_http_crawl_targets.py --url http://127.0.0.1:8080/store --count 1000 --concurrency 50
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--count", type=int, choices=(100, 500, 1000), default=100)
    parser.add_argument("--concurrency", type=int, default=25)
    args = parser.parse_args()

    sem = asyncio.Semaphore(args.concurrency)
    counts: dict[int | str, int] = {}
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, limits=httpx.Limits(max_connections=args.concurrency)) as client:
        async def one(i: int) -> None:
            async with sem:
                try:
                    response = await client.get(args.url, headers={"x-stress-request": str(i)})
                    counts[response.status_code] = counts.get(response.status_code, 0) + 1
                except Exception as exc:  # pragma: no cover - benchmark failure path
                    key = type(exc).__name__
                    counts[key] = counts.get(key, 0) + 1

        await asyncio.gather(*(one(i) for i in range(args.count)))

    elapsed = time.perf_counter() - started
    print(f"requests={args.count} concurrency={args.concurrency} elapsed={elapsed:.3f}s rps={args.count / max(elapsed, 0.001):.1f}")
    print("results=" + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))))
    failures = sum(v for k, v in counts.items() if isinstance(k, str) or (isinstance(k, int) and k >= 500))
    if failures:
        raise SystemExit(f"load test observed {failures} client/server failures")


if __name__ == "__main__":
    asyncio.run(main())
