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
    parser.add_argument("--url", required=True, help="API base URL")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--conversation-id", default="rate-limit-stress")
    parser.add_argument("--concurrency", type=int, choices=(100, 500, 1000), default=100)
    parser.add_argument("--requests", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", help="Optional JSON result path")
    args = parser.parse_args()

    total = args.requests or args.concurrency
    url = args.url.rstrip("/") + "/v1/messages/customer/" + args.conversation_id
    sem = asyncio.Semaphore(args.concurrency)
    counts: dict[int | str, int] = {}
    latencies: list[float] = []

    async with httpx.AsyncClient(timeout=args.timeout, limits=httpx.Limits(max_connections=args.concurrency)) as client:
        started = time.perf_counter()

        async def one(i: int) -> None:
            async with sem:
                try:
                    request_started = time.perf_counter()
                    response = await client.get(
                        url,
                        headers={
                            "x-api-key": args.api_key,
                            "x-visitor-id": f"stress-{i}",
                        },
                    )
                    latencies.append(time.perf_counter() - request_started)
                    counts[response.status_code] = counts.get(response.status_code, 0) + 1
                except Exception as exc:  # pragma: no cover - benchmark failure path
                    key = type(exc).__name__
                    counts[key] = counts.get(key, 0) + 1

        await asyncio.gather(*(one(i) for i in range(total)))
        elapsed = time.perf_counter() - started

    report = {
        "requests": total,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "rps": round(total / max(elapsed, 0.001), 1),
        "results": {str(key): value for key, value in counts.items()},
        "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95), "p99": percentile(latencies, 99)},
        "completed_requests": len(latencies),
    }
    print(f"requests={total} concurrency={args.concurrency} elapsed={elapsed:.3f}s rps={report['rps']:.1f}")
    print("results=" + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda x: str(x[0]))))
    print("latency_ms=" + json.dumps(report["latency_ms"], sort_keys=True))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            json.dump(report, output_file, indent=2, sort_keys=True)
    if counts.get(500) or counts.get(502) or counts.get(503):
        raise SystemExit("server-side failures detected")


if __name__ == "__main__":
    asyncio.run(main())
