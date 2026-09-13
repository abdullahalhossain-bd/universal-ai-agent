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
import json
import time

import httpx


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((percentile_value / 100) * (len(ordered) - 1))))
    return round(ordered[index] * 1000, 2)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--count", type=int, choices=(100, 500, 1000), default=100)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", help="Optional JSON result path")
    args = parser.parse_args()

    sem = asyncio.Semaphore(args.concurrency)
    counts: dict[int | str, int] = {}
    latencies: list[float] = []
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=False, limits=httpx.Limits(max_connections=args.concurrency)) as client:
        async def one(i: int) -> None:
            async with sem:
                try:
                    request_started = time.perf_counter()
                    response = await client.get(args.url, headers={"x-stress-request": str(i)})
                    latencies.append(time.perf_counter() - request_started)
                    counts[response.status_code] = counts.get(response.status_code, 0) + 1
                except Exception as exc:  # pragma: no cover - benchmark failure path
                    key = type(exc).__name__
                    counts[key] = counts.get(key, 0) + 1

        await asyncio.gather(*(one(i) for i in range(args.count)))

    elapsed = time.perf_counter() - started
    report = {
        "requests": args.count,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "rps": round(args.count / max(elapsed, 0.001), 1),
        "results": {str(key): value for key, value in counts.items()},
        "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95), "p99": percentile(latencies, 99)},
        "completed_requests": len(latencies),
    }
    print(f"requests={args.count} concurrency={args.concurrency} elapsed={elapsed:.3f}s rps={report['rps']:.1f}")
    print("results=" + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))))
    print("latency_ms=" + json.dumps(report["latency_ms"], sort_keys=True))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            json.dump(report, output_file, indent=2, sort_keys=True)
    failures = sum(v for k, v in counts.items() if isinstance(k, str) or (isinstance(k, int) and k >= 500))
    if failures:
        raise SystemExit(f"load test observed {failures} client/server failures")


if __name__ == "__main__":
    asyncio.run(main())
