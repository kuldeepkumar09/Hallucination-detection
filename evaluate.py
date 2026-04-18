#!/usr/bin/env python3
"""
Hallucination Detection Evaluation Harness

Measures precision, recall, and F1 against a labeled YAML test set.
Produces a detailed JSON report and a Rich terminal summary.

Usage:
  python evaluate.py --cases eval_cases.yaml
  python evaluate.py --cases eval_cases.yaml --output report.json --verbose

Input YAML format (eval_cases.yaml):
  cases:
    - id: "medical_001"
      text: "Ibuprofen is safe during all trimesters of pregnancy."
      expected_hallucinations:          # substrings of claims that ARE hallucinations
        - "Ibuprofen is safe during all trimesters"
      expected_actions: ["block"]       # acceptable actions: pass, annotate, flag, block

    - id: "geo_001"
      text: "Paris is the capital of France."
      expected_hallucinations: []       # correct fact — no hallucinations
      expected_actions: ["pass", "annotate"]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import yaml
except ImportError:
    print("Error: pyyaml not installed.  Run: pip install pyyaml")
    sys.exit(1)

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

HALLUCINATION_ACTIONS = {"flag", "block"}
CLEAN_ACTIONS = {"pass", "annotate"}


def _text_matches(claim_text: str, expected_substrings: List[str]) -> bool:
    """Return True if claim_text contains any of the expected substrings (case-insensitive)."""
    low = claim_text.lower()
    return any(sub.lower() in low for sub in expected_substrings)


def evaluate_case(
    case: Dict[str, Any],
    audit,
) -> Dict[str, Any]:
    """
    Compare pipeline output against a labeled test case.
    Returns a result dict with TP/FP/FN/TN per claim.
    """
    expected_hallucinations: List[str] = case.get("expected_hallucinations", [])
    expected_actions: List[str] = [a.lower() for a in case.get("expected_actions", [])]

    result = {
        "id": case["id"],
        "text": case["text"][:100],
        "expected_hallucinations": expected_hallucinations,
        "expected_actions": expected_actions,
        "total_claims": audit.total_claims,
        "overall_confidence": audit.overall_confidence,
        "response_blocked": audit.response_blocked,
        "processing_time_ms": audit.processing_time_ms,
        "claims": [],
        "tp": 0, "fp": 0, "fn": 0, "tn": 0,
        "action_correct": False,
        "claim_type_breakdown": defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0}),
    }

    for decision in audit.claims:
        claim_text = decision.verified_claim.claim.text
        claim_type = decision.verified_claim.claim.claim_type.value
        action = decision.action.value
        is_hallucination_action = action in HALLUCINATION_ACTIONS

        # Is this claim actually a hallucination?
        is_actual_hallucination = _text_matches(claim_text, expected_hallucinations)

        record = {
            "text": claim_text[:80],
            "type": claim_type,
            "action": action,
            "confidence": decision.verified_claim.confidence,
            "status": decision.verified_claim.status.value,
            "is_actual_hallucination": is_actual_hallucination,
            "verdict": "",
        }

        if is_actual_hallucination and is_hallucination_action:
            result["tp"] += 1
            record["verdict"] = "TP"
        elif not is_actual_hallucination and is_hallucination_action:
            result["fp"] += 1
            record["verdict"] = "FP"
        elif is_actual_hallucination and not is_hallucination_action:
            result["fn"] += 1
            record["verdict"] = "FN"
        else:
            result["tn"] += 1
            record["verdict"] = "TN"

        result["claims"].append(record)
        ctb = result["claim_type_breakdown"][claim_type]
        ctb[record["verdict"].lower()] += 1

    # Action-level correctness: did the overall response action match expectations?
    if expected_actions:
        # Determine overall response action: blocked > flagged > annotated > passed
        if audit.blocked_count > 0:
            overall_action = "block"
        elif audit.flagged_count > 0:
            overall_action = "flag"
        elif getattr(audit, "annotate_count", 0) > 0:
            overall_action = "annotate"
        else:
            overall_action = "pass"
        result["action_correct"] = overall_action in expected_actions
        result["actual_action"] = overall_action
    else:
        result["action_correct"] = True
        result["actual_action"] = "n/a"

    # Handle missed hallucinations (expected but no claim matched)
    has_expected_hallucination = len(expected_hallucinations) > 0
    if has_expected_hallucination and result["tp"] == 0:
        result["fn"] = max(result["fn"], len(expected_hallucinations))

    result["claim_type_breakdown"] = dict(result["claim_type_breakdown"])
    return result


def compute_metrics(results: List[Dict]) -> Dict[str, Any]:
    tp = sum(r["tp"] for r in results)
    fp = sum(r["fp"] for r in results)
    fn = sum(r["fn"] for r in results)
    tn = sum(r["tn"] for r in results)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0
    action_accuracy = sum(1 for r in results if r["action_correct"]) / len(results) if results else 0.0

    avg_conf = sum(r["overall_confidence"] for r in results) / len(results) if results else 0.0
    avg_ms = sum(r["processing_time_ms"] for r in results) / len(results) if results else 0.0

    # Per claim-type breakdown
    type_totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for r in results:
        for ctype, counts in r.get("claim_type_breakdown", {}).items():
            for k, v in counts.items():
                type_totals[ctype][k] += v

    type_metrics: Dict[str, Dict] = {}
    for ctype, counts in type_totals.items():
        p = counts["tp"] / (counts["tp"] + counts["fp"]) if (counts["tp"] + counts["fp"]) > 0 else 0.0
        r_ = counts["tp"] / (counts["tp"] + counts["fn"]) if (counts["tp"] + counts["fn"]) > 0 else 0.0
        f = 2 * p * r_ / (p + r_) if (p + r_) > 0 else 0.0
        type_metrics[ctype] = {
            "precision": round(p, 3), "recall": round(r_, 3), "f1": round(f, 3),
            **counts,
        }

    return {
        "total_cases": len(results),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round(accuracy, 3),
        "action_accuracy": round(action_accuracy, 3),
        "avg_confidence": round(avg_conf, 3),
        "avg_processing_ms": round(avg_ms, 1),
        "per_type": type_metrics,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_evaluation(cases_path: str, output_path: str, verbose: bool) -> None:
    with open(cases_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases: List[Dict] = data.get("cases", [])

    if not cases:
        console.print("[red]No cases found in YAML file.[/red]")
        sys.exit(1)

    console.print(f"\n[bold cyan]Hallucination Detection Evaluation[/bold cyan]")
    console.print(f"Cases: [green]{len(cases)}[/green]  |  File: [dim]{cases_path}[/dim]\n")

    from hallucination_middleware import HallucinationDetectionPipeline  # noqa: PLC0415
    pipeline = HallucinationDetectionPipeline()

    results: List[Dict] = []
    for i, case in enumerate(cases, 1):
        case_id = case.get("id", f"case_{i}")
        with console.status(f"[{i}/{len(cases)}] Running '{case_id}' ..."):
            audit = await pipeline.process(case["text"], model="eval")
        result = evaluate_case(case, audit)
        results.append(result)

        verdict_icon = "OK" if result["tp"] > 0 or (not case.get("expected_hallucinations") and result["fp"] == 0) else "MISS"
        console.print(
            f"  [{verdict_icon}] [{i:02d}] {case_id:<20}  "
            f"TP={result['tp']} FP={result['fp']} FN={result['fn']} TN={result['tn']}  "
            f"conf={result['overall_confidence']:.2f}  "
            f"action={result.get('actual_action','?')} "
            + ("[green]correct[/green]" if result["action_correct"] else "[red]wrong[/red]")
        )

        if verbose:
            for c in result["claims"]:
                color = {"TP": "green", "FP": "yellow", "FN": "red", "TN": "dim"}.get(c["verdict"], "white")
                console.print(
                    f"      [{color}]{c['verdict']}[/{color}] [{c['action'].upper():<8}] "
                    f"conf={c['confidence']:.2f}  {c['text'][:60]}"
                )

    metrics = compute_metrics(results)

    # ── Terminal summary ────────────────────────────────────────────────────
    console.print()
    console.rule("[bold]Evaluation Results[/bold]")

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="bold green", justify="right")

    summary.add_row("Total cases",       str(metrics["total_cases"]))
    summary.add_row("True Positives",    str(metrics["tp"]))
    summary.add_row("False Positives",   str(metrics["fp"]))
    summary.add_row("False Negatives",   str(metrics["fn"]))
    summary.add_row("True Negatives",    str(metrics["tn"]))
    summary.add_row("", "")
    summary.add_row("Precision",         f"{metrics['precision']:.3f}")
    summary.add_row("Recall",            f"{metrics['recall']:.3f}")
    summary.add_row("F1 Score",          f"{metrics['f1']:.3f}")
    summary.add_row("Accuracy",          f"{metrics['accuracy']:.3f}")
    summary.add_row("Action Accuracy",   f"{metrics['action_accuracy']:.3f}")
    summary.add_row("", "")
    summary.add_row("Avg Confidence",    f"{metrics['avg_confidence']:.3f}")
    summary.add_row("Avg Processing ms", f"{metrics['avg_processing_ms']:.1f}")
    console.print(summary)

    if metrics["per_type"]:
        console.print()
        type_table = Table(title="Per Claim-Type Breakdown", box=box.SIMPLE_HEAD, header_style="bold blue")
        type_table.add_column("Type", style="blue")
        type_table.add_column("P", justify="right")
        type_table.add_column("R", justify="right")
        type_table.add_column("F1", justify="right")
        type_table.add_column("TP", justify="right", style="green")
        type_table.add_column("FP", justify="right", style="yellow")
        type_table.add_column("FN", justify="right", style="red")
        type_table.add_column("TN", justify="right", style="dim")

        for ctype, m in sorted(metrics["per_type"].items()):
            type_table.add_row(
                ctype,
                f"{m['precision']:.2f}", f"{m['recall']:.2f}", f"{m['f1']:.2f}",
                str(m["tp"]), str(m["fp"]), str(m["fn"]), str(m["tn"]),
            )
        console.print(type_table)

    # ── Write JSON report ───────────────────────────────────────────────────
    report = {"metrics": metrics, "cases": results}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    console.print(f"\n[dim]Report saved to: {output_path}[/dim]\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate hallucination detection accuracy against labeled test cases."
    )
    parser.add_argument("--cases", required=True, help="Path to eval_cases.yaml")
    parser.add_argument("--output", default="eval_report.json", help="Output JSON report path")
    parser.add_argument("--verbose", action="store_true", help="Show per-claim verdicts")
    args = parser.parse_args()

    if not Path(args.cases).exists():
        console.print(f"[red]File not found: {args.cases}[/red]")
        sys.exit(1)

    asyncio.run(run_evaluation(args.cases, args.output, args.verbose))


if __name__ == "__main__":
    main()
