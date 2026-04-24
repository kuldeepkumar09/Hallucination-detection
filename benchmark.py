#!/usr/bin/env python3
"""
Hallucination Detection Middleware — Performance Benchmark

Measures:
  - Per-stage latency: extraction, verification, decision, self-correction
  - Throughput: claims/second
  - Cache hit rate
  - p50/p95/p99 latency percentiles

Usage:
  python benchmark.py                     # quick run (4 texts)
  python benchmark.py --output results.json
  python benchmark.py --runs 10           # more iterations for stable percentiles
"""
import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.WARNING)  # suppress pipeline noise during benchmark

# ---------------------------------------------------------------------------
# Test texts — cover multiple domains to exercise different thresholds
# ---------------------------------------------------------------------------

BENCHMARK_TEXTS = [
    # MEDICAL — high stakes, strict threshold
    (
        "ibuprofen_medical",
        "Ibuprofen is safe in all trimesters of pregnancy and can be used freely. "
        "The recommended adult dose is 800mg every 12 hours for pain relief. "
        "Penicillin was discovered by Alexander Fleming in 1928, leading to the antibiotic era.",
    ),
    # LEGAL / FINANCIAL
    (
        "gdpr_financial",
        "The GDPR came into effect on 25 May 2018 in the European Union. "
        "The maximum fine under GDPR is €20 million or 4% of global annual turnover, whichever is higher. "
        "The 2008 financial crisis caused US GDP to fall by approximately 30%.",
    ),
    # SCIENCE / HISTORY — general domain
    (
        "science_history",
        "Albert Einstein was born on 14 March 1879 in Berlin, Germany. "
        "He published his Special Theory of Relativity in 1912. "
        "Einstein won the Nobel Prize in Physics for the discovery of the law of the photoelectric effect.",
    ),
    # TECH — general domain, mostly correct
    (
        "tech_history",
        "The World Wide Web was invented by Tim Berners-Lee in 1989 at CERN. "
        "The first iPhone was released by Apple in June 2007. "
        "Google was founded by Larry Page and Sergey Brin in 1998.",
    ),
]


async def _run_single(pipeline, text: str) -> dict:
    """Run pipeline on one text, return timing breakdown."""
    stage_times: dict = {}
    t_total = time.monotonic()

    # Stage 1: extraction
    t0 = time.monotonic()
    claims = await pipeline._extractor.extract(text)
    stage_times["extraction_ms"] = (time.monotonic() - t0) * 1000

    if not claims:
        return {
            "n_claims": 0,
            "extraction_ms": stage_times["extraction_ms"],
            "verification_ms": 0,
            "decision_ms": 0,
            "correction_ms": 0,
            "total_ms": (time.monotonic() - t_total) * 1000,
            "cache_hits": 0,
        }

    # Stage 2: verification
    t0 = time.monotonic()
    verified_claims, retrieval_meta = await pipeline._verifier.verify(claims)
    stage_times["verification_ms"] = (time.monotonic() - t0) * 1000

    cache_hits = sum(1 for m in retrieval_meta if m.cache_hit)

    # Stage 3: decision
    t0 = time.monotonic()
    decisions = pipeline._decision_engine.decide(verified_claims)
    stage_times["decision_ms"] = (time.monotonic() - t0) * 1000

    # Stage 4: self-correction (only if there are issues)
    correction_ms = 0.0
    if any(d.action.value in ("block", "flag") for d in decisions):
        t0 = time.monotonic()
        await pipeline._corrector.correct(text, decisions)
        correction_ms = (time.monotonic() - t0) * 1000

    stage_times["correction_ms"] = correction_ms
    stage_times["total_ms"] = (time.monotonic() - t_total) * 1000
    stage_times["n_claims"] = len(claims)
    stage_times["cache_hits"] = cache_hits
    return stage_times


def _percentile(data: list, p: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    idx = (len(data) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
    return round(data[lo] + (data[hi] - data[lo]) * (idx - lo), 1)


async def run_benchmark(runs: int = 4, output_path: str = "") -> dict:
    from hallucination_middleware.pipeline import HallucinationDetectionPipeline

    print(f"\n{'=' * 60}")
    print("  Hallucination Detection Middleware — Benchmark")
    print(f"{'=' * 60}")
    print(f"  Runs per text: {runs}  |  Texts: {len(BENCHMARK_TEXTS)}")
    print(f"  Provider: {os.environ.get('LLM_PROVIDER', 'ollama')}")
    print(f"{'=' * 60}\n")

    pipeline = HallucinationDetectionPipeline()

    all_results = {}
    total_latencies = []
    total_cache_hits = 0
    total_claims_processed = 0

    for name, text in BENCHMARK_TEXTS:
        print(f"  [{name}] Running {runs} iterations …", end="", flush=True)
        run_times = []
        for i in range(runs):
            result = await _run_single(pipeline, text)
            run_times.append(result)
            total_latencies.append(result["total_ms"])
            total_cache_hits += result["cache_hits"]
            total_claims_processed += result["n_claims"]
            print(".", end="", flush=True)
        print(" done")

        all_results[name] = {
            "n_claims_avg": round(statistics.mean(r["n_claims"] for r in run_times), 1),
            "extraction_ms_avg": round(statistics.mean(r["extraction_ms"] for r in run_times), 1),
            "verification_ms_avg": round(statistics.mean(r["verification_ms"] for r in run_times), 1),
            "decision_ms_avg": round(statistics.mean(r["decision_ms"] for r in run_times), 1),
            "correction_ms_avg": round(statistics.mean(r["correction_ms"] for r in run_times), 1),
            "total_ms_avg": round(statistics.mean(r["total_ms"] for r in run_times), 1),
            "total_ms_min": round(min(r["total_ms"] for r in run_times), 1),
            "total_ms_max": round(max(r["total_ms"] for r in run_times), 1),
        }

    # Global stats
    cache_hit_rate = (total_cache_hits / max(total_claims_processed, 1)) * 100
    throughput = (total_claims_processed / max(sum(total_latencies) / 1000, 0.001))

    summary = {
        "p50_ms": _percentile(total_latencies, 50),
        "p95_ms": _percentile(total_latencies, 95),
        "p99_ms": _percentile(total_latencies, 99),
        "avg_ms": round(statistics.mean(total_latencies), 1),
        "throughput_claims_per_sec": round(throughput, 2),
        "cache_hit_rate_pct": round(cache_hit_rate, 1),
        "total_claims_processed": total_claims_processed,
        "total_runs": runs * len(BENCHMARK_TEXTS),
    }

    report = {"summary": summary, "per_text": all_results}

    # ---- Print results ----
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  p50 latency  : {summary['p50_ms']} ms")
    print(f"  p95 latency  : {summary['p95_ms']} ms")
    print(f"  p99 latency  : {summary['p99_ms']} ms")
    print(f"  avg latency  : {summary['avg_ms']} ms")
    print(f"  throughput   : {summary['throughput_claims_per_sec']} claims/sec")
    print(f"  cache hit    : {summary['cache_hit_rate_pct']}%")
    print(f"  total claims : {summary['total_claims_processed']}")
    print()
    print(f"  {'Text':<25}  {'Claims':>6}  {'Extract':>8}  {'Verify':>8}  {'Total':>8}")
    print(f"  {'-'*25}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}")
    for name, r in all_results.items():
        print(
            f"  {name:<25}  {r['n_claims_avg']:>6.1f}  "
            f"{r['extraction_ms_avg']:>7.0f}ms  {r['verification_ms_avg']:>7.0f}ms  "
            f"{r['total_ms_avg']:>7.0f}ms"
        )
    print(f"{'=' * 60}\n")

    if output_path:
        Path(output_path).write_text(json.dumps(report, indent=2))
        print(f"  Results saved to: {output_path}\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark hallucination detection pipeline")
    parser.add_argument("--runs", type=int, default=4, help="Iterations per text (default: 4)")
    parser.add_argument("--output", type=str, default="", help="Save JSON results to this path")
    args = parser.parse_args()
    asyncio.run(run_benchmark(runs=args.runs, output_path=args.output))


if __name__ == "__main__":
    main()
