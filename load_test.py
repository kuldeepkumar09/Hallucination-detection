"""
Async load test for HalluCheck proxy.

Usage:
    python load_test.py [--url URL] [--key KEY] [--concurrency N] [--requests N] [--timeout N]

Examples:
    python load_test.py --url http://localhost:8080 --key hallu-dev-secret-2024
    python load_test.py --concurrency 30 --requests 300 --timeout 60

Metrics reported:
    - Total requests / success / error counts
    - Requests per second (RPS)
    - P50 / P90 / P99 latency
    - Error rate
    - Per-status-code breakdown
"""
import argparse
import asyncio
import statistics
import sys
import time
from collections import Counter
from typing import List, Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required — install it with: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Sample texts to verify — varied length and hallucination density
# ---------------------------------------------------------------------------
_SAMPLE_TEXTS = [
    "Einstein won the Nobel Prize for his theory of relativity in 1921.",
    "The Wright Brothers made their first flight at Kitty Hawk, North Carolina, in 1903.",
    "Python was created by Guido van Rossum and first released in 1991.",
    "The capital of Australia is Sydney and it is the largest city in the country.",
    "Marie Curie discovered radium and polonium and was the first person to win two Nobel Prizes.",
    "The Amazon River is the longest river in the world, stretching over 6,000 kilometres.",
    "Shakespeare was born in Stratford-upon-Avon in 1564 and died on April 23, 1616.",
    "The human body has approximately 206 bones in adulthood.",
    "Penicillin was discovered by Alexander Fleming in 1928 when he noticed mould killing bacteria.",
    "The Berlin Wall fell on November 9, 1989, ending the division of East and West Germany.",
    "DNA has a double-helix structure first described by Watson and Crick in 1953.",
    "The first iPhone was released by Apple in June 2007 and it changed the smartphone industry.",
]


async def _single_request(
    client: httpx.AsyncClient,
    url: str,
    key: str,
    text: str,
    timeout: float,
) -> dict:
    """Fire one /verify request and return timing + status info."""
    t0 = time.monotonic()
    status = 0
    error: Optional[str] = None
    try:
        resp = await client.post(
            f"{url}/verify",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={"text": text},
            timeout=timeout,
        )
        status = resp.status_code
    except httpx.TimeoutException:
        error = "timeout"
    except httpx.ConnectError:
        error = "connect_error"
    except Exception as exc:
        error = str(exc)[:80]

    elapsed = time.monotonic() - t0
    return {"latency": elapsed, "status": status, "error": error}


async def _worker(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    url: str,
    key: str,
    texts: List[str],
    results: list,
    idx: int,
    timeout: float,
) -> None:
    text = texts[idx % len(texts)]
    async with sem:
        r = await _single_request(client, url, key, text, timeout)
    results.append(r)


async def run_load_test(
    url: str,
    key: str,
    concurrency: int,
    total_requests: int,
    timeout: float,
) -> None:
    print(f"\nHalluCheck Load Test")
    print(f"  URL:         {url}/verify")
    print(f"  Concurrency: {concurrency}")
    print(f"  Requests:    {total_requests}")
    print(f"  Timeout:     {timeout}s")
    print()

    results: list = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        # Warmup: 1 request to check connectivity
        warmup = await _single_request(client, url, key, _SAMPLE_TEXTS[0], timeout)
        if warmup["error"] or warmup["status"] not in (200, 201):
            print(f"WARMUP FAILED — status={warmup['status']} error={warmup['error']}")
            print("Is the server running? Check: uvicorn hallucination_middleware.proxy:app --port 8080")
            return

        print(f"Warmup OK (status={warmup['status']}, latency={warmup['latency']:.2f}s)")
        print(f"Running {total_requests} requests at concurrency={concurrency}...\n")

        t_start = time.monotonic()
        tasks = [
            _worker(sem, client, url, key, _SAMPLE_TEXTS, results, i, timeout)
            for i in range(total_requests)
        ]

        # Show progress every 10% of requests
        chunk = max(1, total_requests // 10)
        for i in range(0, total_requests, chunk):
            batch = tasks[i:i + chunk]
            await asyncio.gather(*batch)
            done = min(i + chunk, total_requests)
            pct = done / total_requests * 100
            print(f"  {done:>4}/{total_requests}  ({pct:5.1f}%)  completed so far")

        duration = time.monotonic() - t_start

    # ---------------------------------------------------------------------------
    # Compute stats
    # ---------------------------------------------------------------------------
    latencies = [r["latency"] for r in results]
    statuses = Counter(r["status"] for r in results)
    errors = [r for r in results if r["error"]]
    successes = [r for r in results if not r["error"] and r["status"] == 200]

    p50 = statistics.median(latencies)
    p90 = sorted(latencies)[int(len(latencies) * 0.90)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]
    rps = len(results) / duration
    error_rate = len(errors) / len(results) * 100

    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"  Requests:      {len(results)} total / {len(successes)} succeeded / {len(errors)} errors")
    print(f"  Duration:      {duration:.1f}s")
    print(f"  RPS:           {rps:.1f}")
    print(f"  P50 latency:   {p50:.2f}s")
    print(f"  P90 latency:   {p90:.2f}s")
    print(f"  P99 latency:   {p99:.2f}s")
    print(f"  Min latency:   {min(latencies):.2f}s")
    print(f"  Max latency:   {max(latencies):.2f}s")
    print(f"  Error rate:    {error_rate:.1f}%")
    print()
    print("  Status codes:")
    for code, count in sorted(statuses.items()):
        print(f"    {code}: {count}")
    if errors:
        print()
        print("  Error types:")
        error_types = Counter(r["error"] for r in errors)
        for err, count in error_types.most_common(5):
            print(f"    {err}: {count}")
    print("=" * 50)

    # Grade the performance
    if p90 < 5.0 and error_rate < 1.0:
        grade = "EXCELLENT"
    elif p90 < 10.0 and error_rate < 5.0:
        grade = "GOOD"
    elif p90 < 20.0 and error_rate < 10.0:
        grade = "ACCEPTABLE"
    else:
        grade = "NEEDS IMPROVEMENT"
    print(f"\n  Performance grade: {grade}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="HalluCheck async load test")
    parser.add_argument("--url", default="http://localhost:8080", help="Proxy base URL")
    parser.add_argument("--key", default="hallu-dev-secret-2024", help="API key (x-api-key)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--requests", type=int, default=50, help="Total requests to send")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-request timeout (seconds)")
    args = parser.parse_args()

    asyncio.run(run_load_test(
        url=args.url,
        key=args.key,
        concurrency=args.concurrency,
        total_requests=args.requests,
        timeout=args.timeout,
    ))


if __name__ == "__main__":
    main()
