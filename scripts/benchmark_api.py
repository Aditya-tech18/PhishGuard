#!/usr/bin/env python3
"""Bounded loopback-only API benchmark. Does not open or scan any target website.

Use a dedicated local service with an explicitly suitable rate limit. A benchmark never
changes server configuration or bypasses its quota. Reports contain aggregate timing/status
counts only, not payloads, keys, client addresses or response bodies.
"""

import argparse
import asyncio
from collections import Counter
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time
import httpx
from phishguard.common.files import atomic_json


SAMPLES = [
    "https://example.com/",
    "https://example.org/about",
    "http://verify-account.test/login/secure",
    "https://ordinary-site.test/contact",
]


def summarize(durations, statuses, elapsed, concurrency, model_version):
    if not durations or any(not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Finite nonnegative timing samples required")
    values = sorted(durations)

    def percentile(fraction):
        position = fraction * (len(values) - 1)
        left = int(position)
        right = min(left + 1, len(values) - 1)
        return (values[left] + (values[right] - values[left]) * (position - left)) * 1000

    return {
        "requests": len(durations),
        "concurrency": concurrency,
        "elapsed_seconds": elapsed,
        "requests_per_second": len(durations) / max(elapsed, 1e-9),
        "latency_ms": {
            "mean": statistics.mean(values) * 1000,
            "p50": percentile(0.5),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
            "max": max(values) * 1000,
        },
        "status_counts": dict(Counter(map(str, statuses))),
        "model_version": model_version,
        "environment": {"machine": platform.machine(), "python": platform.python_version()},
        "scope": "loopback single-service experiment, not a public capacity or availability guarantee",
    }


async def benchmark(port, key, count=200, concurrency=8):
    if not 1024 <= port <= 65535 or not 1 <= count <= 10000 or not 1 <= concurrency <= 64:
        raise ValueError("Benchmark limits exceeded")
    if len(key) < 32:
        raise ValueError("A configured API key is required")
    base = f"http://127.0.0.1:{port}"
    durations, statuses = [], []
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        timeout=30,
        trust_env=False,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=concurrency),
    ) as client:
        health = await client.get(base + "/health")
        health.raise_for_status()
        version = health.json()["model_version"]

        async def request(index):
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post(
                        base + "/api/v1/predict/url",
                        headers={"X-API-Key": key},
                        json={"url": SAMPLES[index % len(SAMPLES)]},
                    )
                    status = response.status_code
                    if status == 200 and response.json().get("model_version") != version:
                        raise RuntimeError("Model changed during the benchmark")
                except httpx.HTTPError:
                    status = "transport_error"
                durations.append(time.perf_counter() - started)
                statuses.append(status)

        started = time.perf_counter()
        await asyncio.gather(*(request(index) for index in range(count)))
        elapsed = time.perf_counter() - started
    return summarize(durations, statuses, elapsed, concurrency, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(
        benchmark(
            args.port, os.environ.get("PHISHGUARD_API_KEY", ""), args.requests, args.concurrency
        )
    )
    atomic_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
