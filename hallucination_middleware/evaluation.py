"""
Benchmark evaluation for HalluCheck.

Ground-truth dataset: 25 claims, each labelled TRUE or FALSE.
A claim labelled FALSE is a known hallucination that the pipeline should flag/block.
A claim labelled TRUE should pass as verified/supported.

Run via: POST /evaluate   (no request body needed)
Returns: precision, recall, F1, accuracy, and per-claim details.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkClaim:
    text: str
    ground_truth: bool  # True = factually correct, False = hallucination


# ---------------------------------------------------------------------------
# Ground-truth dataset
# TRUE claims are well-established facts.
# FALSE claims are common LLM hallucinations (wrong dates, wrong people, etc.)
# ---------------------------------------------------------------------------
BENCHMARK_CLAIMS: List[BenchmarkClaim] = [
    # History — TRUE
    BenchmarkClaim("World War II ended in 1945.", True),
    BenchmarkClaim("The Berlin Wall fell in 1989.", True),
    BenchmarkClaim("Neil Armstrong was the first human to walk on the Moon in 1969.", True),
    BenchmarkClaim("The French Revolution began in 1789.", True),
    BenchmarkClaim("Albert Einstein was born in Ulm, Germany, in 1879.", True),

    # History — FALSE (hallucinations)
    BenchmarkClaim("World War I ended in 1919 with the signing of the Treaty of Versailles in Paris.", False),  # Treaty signed in Versailles, not Paris
    BenchmarkClaim("Abraham Lincoln was the 16th President and was born in Illinois.", False),  # born in Kentucky
    BenchmarkClaim("The Wright Brothers made their first powered flight in 1903 at Kitty Hawk, South Carolina.", False),  # North Carolina
    BenchmarkClaim("Christopher Columbus landed in North America in 1492.", False),  # Caribbean / Bahamas

    # Science — TRUE
    BenchmarkClaim("The speed of light in a vacuum is approximately 299,792 kilometers per second.", True),
    BenchmarkClaim("DNA has a double-helix structure.", True),
    BenchmarkClaim("The human body has 206 bones in adulthood.", True),

    # Science — FALSE
    BenchmarkClaim("Water boils at 90 degrees Celsius at sea level.", False),  # 100 °C
    BenchmarkClaim("The human genome contains approximately 3 billion base pairs and about 100,000 protein-coding genes.", False),  # ~20,000–25,000 genes
    BenchmarkClaim("Albert Einstein received the Nobel Prize for his theory of relativity.", False),  # for the photoelectric effect

    # Technology — TRUE
    BenchmarkClaim("Python was created by Guido van Rossum and first released in 1991.", True),
    BenchmarkClaim("The first iPhone was released by Apple in 2007.", True),
    BenchmarkClaim("Linux was created by Linus Torvalds in 1991.", True),

    # Technology — FALSE
    BenchmarkClaim("Python was created by James Gosling and first released in 1995.", False),  # Gosling created Java
    BenchmarkClaim("The World Wide Web was invented by Bill Gates in 1989.", False),  # Tim Berners-Lee
    BenchmarkClaim("The first commercial smartphone was released by Nokia in 1994.", False),  # IBM Simon

    # Geography — TRUE
    BenchmarkClaim("Mount Everest is the highest mountain on Earth above sea level.", True),
    BenchmarkClaim("The Amazon River is the largest river by discharge volume in the world.", True),

    # Geography — FALSE
    BenchmarkClaim("The Mississippi River is the longest river in the world at over 6,000 miles.", False),  # ~2,340 miles; Amazon/Nile are longest
    BenchmarkClaim("Australia is both a country and the largest continent on Earth.", False),  # Antarctica / Asia / Africa are larger
    BenchmarkClaim("Mount Everest is located in the Alps mountain range.", False),  # Himalayas
    BenchmarkClaim("The capital of Australia is Sydney.", False),  # Canberra
    BenchmarkClaim("Humans use only 10 percent of their brain at any given time.", False),  # debunked neuroscience myth
]


@dataclass
class EvaluationResult:
    total: int = 0
    true_positives: int = 0   # hallucination correctly flagged/blocked
    false_positives: int = 0  # correct claim wrongly flagged/blocked
    true_negatives: int = 0   # correct claim correctly passed
    false_negatives: int = 0  # hallucination that slipped through
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0
    details: List[dict] = field(default_factory=list)


async def evaluate_accuracy(pipeline, max_claims: Optional[int] = None) -> EvaluationResult:
    """
    Run BENCHMARK_CLAIMS through the pipeline and compute detection metrics.

    Positive class = hallucination (ground_truth=False).
    Predicted positive = pipeline assigned BLOCK or FLAG to any claim in the text.

    Args:
        pipeline : HallucinationDetectionPipeline instance
        max_claims: cap number of benchmark items (useful for quick smoke-tests)

    Returns:
        EvaluationResult with precision, recall, F1, accuracy, and per-item details
    """
    claims = BENCHMARK_CLAIMS[:max_claims] if max_claims else BENCHMARK_CLAIMS
    result = EvaluationResult(total=len(claims))

    async def _run_one(bc: BenchmarkClaim) -> dict:
        try:
            audit = await pipeline.process(bc.text)
            detected = audit.flagged_count + audit.blocked_count > 0
        except Exception as exc:
            logger.warning("[eval] pipeline error for '%s': %s", bc.text[:60], exc)
            detected = False

        is_hallucination = not bc.ground_truth
        tp = detected and is_hallucination
        fp = detected and not is_hallucination
        tn = not detected and not is_hallucination
        fn = not detected and is_hallucination

        return {
            "claim": bc.text,
            "ground_truth": bc.ground_truth,
            "detected_as_hallucination": detected,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        }

    # Run all benchmark items concurrently (pipeline has its own concurrency semaphore)
    rows = await asyncio.gather(*[_run_one(bc) for bc in claims])

    for row in rows:
        result.details.append(row)
        if row["tp"]: result.true_positives += 1
        elif row["fp"]: result.false_positives += 1
        elif row["tn"]: result.true_negatives += 1
        elif row["fn"]: result.false_negatives += 1

    tp, fp, fn, tn = (
        result.true_positives, result.false_positives,
        result.false_negatives, result.true_negatives,
    )
    result.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    result.recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    result.f1        = (
        2 * result.precision * result.recall / (result.precision + result.recall)
        if (result.precision + result.recall) > 0 else 0.0
    )
    result.accuracy  = (tp + tn) / result.total if result.total > 0 else 0.0

    logger.info(
        "[eval] P=%.3f R=%.3f F1=%.3f Acc=%.3f (TP=%d FP=%d FN=%d TN=%d)",
        result.precision, result.recall, result.f1, result.accuracy,
        tp, fp, fn, tn,
    )
    return result
