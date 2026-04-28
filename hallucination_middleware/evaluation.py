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

# ---------------------------------------------------------------------------
# Adversarial benchmark — designed to defeat naive detectors.
# Each claim is plausible-sounding, confidently stated, or subtly wrong in a
# way that requires precise factual knowledge to catch.
#
# Categories:
#   PLAUSIBLE   — true-sounding but false (confident LLM-style hallucinations)
#   ATTRIBUTION — right fact, wrong person/date/detail
#   STAT-TRAP   — plausible number that is wrong
#   MULTI-HOP   — requires combining two facts to evaluate correctly
#   TRUE        — looks suspicious but is actually correct (tests false-positive rate)
# ---------------------------------------------------------------------------
ADVERSARIAL_CLAIMS: List[BenchmarkClaim] = [
    # PLAUSIBLE — FALSE
    BenchmarkClaim(
        "Marie Curie won the Nobel Prize in Chemistry in 1903.",
        False,  # Chemistry was 1911; Physics was 1903
    ),
    BenchmarkClaim(
        "Nikola Tesla died a wealthy man after selling his patents to Westinghouse.",
        False,  # Tesla died penniless in a Manhattan hotel room in 1943
    ),
    BenchmarkClaim(
        "Napoleon Bonaparte was unusually short for his era, standing at approximately 5 feet 2 inches.",
        False,  # He was ~5'7" (170 cm); the "short" myth came from British propaganda
    ),
    BenchmarkClaim(
        "The Amazon rainforest produces approximately 20 percent of the world's oxygen.",
        False,  # Widely repeated myth; net O2 from Amazon is near zero (consumed by decomposition)
    ),
    BenchmarkClaim(
        "Einstein was older than Planck, having been born in 1879 versus Planck's birth in 1858.",
        False,  # Logic inverted — Planck (1858) was older than Einstein (1879)
    ),
    BenchmarkClaim(
        "The structure of DNA was first described by Watson, Crick, and Franklin in a 1953 paper in Nature.",
        False,  # Franklin was NOT a co-author on the Watson-Crick Nature paper
    ),

    # ATTRIBUTION — right fact, wrong person/date
    BenchmarkClaim(
        "Gravity was first mathematically described by Isaac Newton in his 1687 Principia Mathematica.",
        True,   # TRUE — Principia Mathematica published 1687
    ),
    BenchmarkClaim(
        "Penicillin was discovered by Alexander Fleming in 1928.",
        True,   # TRUE
    ),

    # STAT-TRAP — plausible but wrong numbers
    BenchmarkClaim(
        "Light takes approximately 8 minutes and 20 seconds to travel from the Sun to Earth.",
        True,   # TRUE — ~499 seconds = 8m 19s ≈ 8m 20s
    ),
    BenchmarkClaim(
        "The human body contains approximately 37 trillion cells.",
        True,   # TRUE — current scientific consensus estimate
    ),

    # TRUE — looks suspicious, is actually correct (false-positive traps)
    BenchmarkClaim(
        "Marie Curie was the first woman to win a Nobel Prize, which she received in Physics in 1903.",
        True,   # TRUE — commonly doubted but correct
    ),
    BenchmarkClaim(
        "The Declaration of Independence was signed on July 4, 1776.",
        True,   # TRUE — commonly questioned but correct
    ),
    BenchmarkClaim(
        "Shakespeare was born and died on the same calendar date, April 23.",
        True,   # TRUE — born April 23, 1564; died April 23, 1616
    ),
    BenchmarkClaim(
        "The telephone patent was filed by Alexander Graham Bell on February 14, 1876.",
        True,   # TRUE
    ),
    BenchmarkClaim(
        "The first iPhone was released by Apple on June 29, 2007.",
        True,   # TRUE
    ),

    # MULTI-HOP — requires combining two facts
    BenchmarkClaim(
        "Germany won the most gold medals at the 1936 Berlin Olympics.",
        True,   # TRUE — Germany: 36 gold, USA: 24 gold
    ),
]

# Full combined benchmark — used when adversarial=True
ALL_BENCHMARK_CLAIMS: List[BenchmarkClaim] = BENCHMARK_CLAIMS + ADVERSARIAL_CLAIMS


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


async def evaluate_accuracy(
    pipeline,
    max_claims: Optional[int] = None,
    adversarial: bool = False,
) -> EvaluationResult:
    """
    Run benchmark claims through the pipeline and compute detection metrics.

    Positive class = hallucination (ground_truth=False).
    Predicted positive = pipeline assigned BLOCK or FLAG to any claim in the text.

    Args:
        pipeline    : HallucinationDetectionPipeline instance
        max_claims  : cap number of benchmark items (useful for quick smoke-tests)
        adversarial : if True, uses ALL_BENCHMARK_CLAIMS (standard + adversarial set)

    Returns:
        EvaluationResult with precision, recall, F1, accuracy, and per-item details
    """
    source = ALL_BENCHMARK_CLAIMS if adversarial else BENCHMARK_CLAIMS
    claims = source[:max_claims] if max_claims else source
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


# ---------------------------------------------------------------------------
# Empirical LLM evaluation
# Sends prompts that LLMs are known to hallucinate on to the configured
# provider, then verifies the actual responses through the pipeline.
# Ground-truth: does the prompt contain a known false premise that the LLM
# is likely to repeat? (hallucination_expected=True/False)
# ---------------------------------------------------------------------------

@dataclass
class LLMEvalPrompt:
    prompt: str
    hallucination_expected: bool  # True = LLM likely to hallucinate in response
    category: str = "GENERAL"


LLM_EVAL_PROMPTS: List[LLMEvalPrompt] = [
    # LLMs commonly hallucinate on these — repeat wrong facts with confidence
    LLMEvalPrompt(
        "Tell me about Einstein's Nobel Prize and what he won it for.",
        hallucination_expected=True,  # often says "relativity"
        category="SCIENCE",
    ),
    LLMEvalPrompt(
        "What year did Napoleon die and what was he known for?",
        hallucination_expected=True,  # often says wrong date or wrong height
        category="HISTORY",
    ),
    LLMEvalPrompt(
        "How long is the Great Wall of China?",
        hallucination_expected=True,  # wildly varying wrong answers
        category="GEOGRAPHY",
    ),
    LLMEvalPrompt(
        "Who invented the telephone and when was the patent filed?",
        hallucination_expected=False,  # Bell/1876 — LLMs usually get this right
        category="TECHNOLOGY",
    ),
    LLMEvalPrompt(
        "What is the speed of light?",
        hallucination_expected=False,  # well-known constant — rarely hallucinated
        category="SCIENCE",
    ),
    LLMEvalPrompt(
        "Who discovered penicillin and when?",
        hallucination_expected=False,  # Fleming/1928 — usually correct
        category="SCIENCE",
    ),
    LLMEvalPrompt(
        "Explain what the Amazon rainforest contributes to the world's oxygen supply.",
        hallucination_expected=True,  # commonly repeats the 20% myth
        category="SCIENCE",
    ),
    LLMEvalPrompt(
        "Tell me about Marie Curie's Nobel Prizes.",
        hallucination_expected=True,  # often confuses which prize she won in which year
        category="SCIENCE",
    ),
    LLMEvalPrompt(
        "What is the capital city of Australia?",
        hallucination_expected=True,  # commonly says Sydney
        category="GEOGRAPHY",
    ),
    LLMEvalPrompt(
        "When did World War II end?",
        hallucination_expected=False,  # 1945 — rarely wrong
        category="HISTORY",
    ),
    LLMEvalPrompt(
        "What did Nikola Tesla achieve financially by the end of his life?",
        hallucination_expected=True,  # LLMs often say he was wealthy from Westinghouse
        category="HISTORY",
    ),
    LLMEvalPrompt(
        "How many bones does the adult human body have?",
        hallucination_expected=False,  # 206 — well known
        category="SCIENCE",
    ),
]


@dataclass
class LLMEvaluationResult(EvaluationResult):
    llm_provider: str = ""
    model: str = ""
    sample_outputs: List[dict] = field(default_factory=list)


async def evaluate_llm_empirical(
    pipeline,
    max_prompts: Optional[int] = None,
) -> LLMEvaluationResult:
    """
    Empirical F1 evaluation on real LLM outputs.

    For each prompt in LLM_EVAL_PROMPTS:
      1. Send the prompt to the configured LLM provider (same model as pipeline).
      2. Run the actual LLM response through the hallucination detection pipeline.
      3. Compare detection result against hallucination_expected ground truth.

    Returns LLMEvaluationResult with precision/recall/F1 on real (not synthetic) outputs.
    """
    from .config import get_settings  # noqa: PLC0415
    from openai import AsyncOpenAI    # noqa: PLC0415

    s = get_settings()
    prompts = LLM_EVAL_PROMPTS[:max_prompts] if max_prompts else LLM_EVAL_PROMPTS

    if s.llm_provider == "nvidia_nim":
        client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
        model = s.verifier_model
    elif s.llm_provider in ("together",):
        client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
        model = s.together_verifier_model
    else:
        client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key, timeout=s.request_timeout)
        model = s.verifier_model

    result = LLMEvaluationResult(
        total=len(prompts),
        llm_provider=s.llm_provider,
        model=model,
    )

    async def _run_one(ep: LLMEvalPrompt) -> dict:
        llm_response = ""
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": ep.prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            llm_response = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("[llm-eval] LLM call failed for '%s': %s", ep.prompt[:50], exc)

        detected = False
        if llm_response:
            try:
                audit = await pipeline.process(llm_response)
                detected = audit.flagged_count + audit.blocked_count > 0
            except Exception as exc:
                logger.warning("[llm-eval] pipeline error: %s", exc)

        is_hallucination = ep.hallucination_expected
        tp = detected and is_hallucination
        fp = detected and not is_hallucination
        tn = not detected and not is_hallucination
        fn = not detected and is_hallucination

        return {
            "prompt": ep.prompt,
            "category": ep.category,
            "hallucination_expected": is_hallucination,
            "llm_response_preview": llm_response[:200],
            "detected_as_hallucination": detected,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        }

    rows = await asyncio.gather(*[_run_one(ep) for ep in prompts])

    for row in rows:
        result.sample_outputs.append(row)
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
    result.f1 = (
        2 * result.precision * result.recall / (result.precision + result.recall)
        if (result.precision + result.recall) > 0 else 0.0
    )
    result.accuracy = (tp + tn) / result.total if result.total > 0 else 0.0

    logger.info(
        "[llm-eval] provider=%s model=%s P=%.3f R=%.3f F1=%.3f Acc=%.3f",
        s.llm_provider, model,
        result.precision, result.recall, result.f1, result.accuracy,
    )
    return result
