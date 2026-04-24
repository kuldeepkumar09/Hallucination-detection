"""
CI accuracy gate — no LLM or network calls required.

Verifies that the DecisionEngine produces correct pass/flag/block decisions
for a fixed set of known inputs. Precision and recall must both meet the
thresholds defined in PRECISION_THRESHOLD / RECALL_THRESHOLD.

Decision matrix (from decision_engine.py):
  CONTRADICTED + critical|high stakes          → BLOCK
  CONTRADICTED + medium|low stakes             → FLAG
  UNVERIFIABLE (any stakes)                    → FLAG  (no evidence ≠ wrong)
  PARTIALLY_SUPPORTED (any stakes)             → FLAG  (never BLOCK)
  VERIFIED + confidence < block_threshold + is_critical → BLOCK
  VERIFIED + confidence < flag_threshold       → FLAG
  VERIFIED + confidence ≥ flag_threshold       → ANNOTATE (annotate_verified=True default)
"""
import pytest

from hallucination_middleware.decision_engine import DecisionEngine
from hallucination_middleware.models import (
    ClaimStakes,
    ClaimType,
    DecisionAction,
    ExtractedClaim,
    VerificationStatus,
    VerifiedClaim,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

PRECISION_THRESHOLD = 0.85   # TP / (TP + FP) — don't incorrectly flag good claims
RECALL_THRESHOLD = 0.80      # TP / (TP + FN) — don't miss bad claims

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_engine = DecisionEngine()


def _make_claim(
    text: str = "test claim",
    claim_type: ClaimType = ClaimType.ENTITY,
    stakes: ClaimStakes = ClaimStakes.MEDIUM,
    category: str = "GENERAL",
) -> ExtractedClaim:
    return ExtractedClaim(
        text=text,
        normalized=text,
        claim_type=claim_type,
        stakes=stakes,
        span_start=0,
        span_end=len(text),
        category=category,
    )


def _make_verified(
    claim: ExtractedClaim,
    status: VerificationStatus,
    confidence: float,
) -> VerifiedClaim:
    return VerifiedClaim(claim=claim, status=status, confidence=confidence)


def _decide(
    status: VerificationStatus,
    confidence: float,
    category: str = "GENERAL",
    stakes: ClaimStakes = ClaimStakes.MEDIUM,
) -> DecisionAction:
    claim = _make_claim(category=category, stakes=stakes)
    vc = _make_verified(claim, status, confidence)
    decisions = _engine.decide([vc])
    return decisions[0].action


# ---------------------------------------------------------------------------
# Known-answer test cases:
# (status, confidence, category, stakes, expected_action)
#
# Domain thresholds (from config.py defaults):
#   GENERAL   block=0.40  flag=0.60
#   MEDICAL   block=0.82  flag=0.88
#   LEGAL     block=0.76  flag=0.82
#   FINANCIAL block=0.70  flag=0.76
#
# annotate_verified=True (default) → VERIFIED ≥ flag_threshold → ANNOTATE, not PASS
# BLOCK on VERIFIED only when: confidence < block_threshold AND stakes==CRITICAL
# CONTRADICTED: BLOCK when critical|high, FLAG when medium|low
# UNVERIFIABLE / PARTIALLY_SUPPORTED: always FLAG (never BLOCK)
# ---------------------------------------------------------------------------

CASES = [
    # -- GENERAL domain ---------------------------------------------------
    # Verified above flag_threshold → ANNOTATE (annotate_verified=True)
    (VerificationStatus.VERIFIED,            0.95, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.ANNOTATE),
    (VerificationStatus.VERIFIED,            0.75, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.ANNOTATE),
    # Verified below flag_threshold(0.60) → FLAG
    (VerificationStatus.VERIFIED,            0.50, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.FLAG),
    # Partially supported → always FLAG
    (VerificationStatus.PARTIALLY_SUPPORTED, 0.55, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.FLAG),
    (VerificationStatus.PARTIALLY_SUPPORTED, 0.25, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.FLAG),
    # Contradicted + medium → FLAG (only critical/high → BLOCK)
    (VerificationStatus.CONTRADICTED,        0.10, "GENERAL", ClaimStakes.MEDIUM,   DecisionAction.FLAG),
    # Contradicted + high → BLOCK
    (VerificationStatus.CONTRADICTED,        0.10, "GENERAL", ClaimStakes.HIGH,     DecisionAction.BLOCK),
    # Unverifiable → always FLAG
    (VerificationStatus.UNVERIFIABLE,        0.30, "GENERAL", ClaimStakes.LOW,      DecisionAction.FLAG),

    # -- MEDICAL domain — block=0.82, flag=0.88 --------------------------
    # Verified above flag_threshold(0.88) → ANNOTATE
    (VerificationStatus.VERIFIED,            0.95, "MEDICAL", ClaimStakes.CRITICAL, DecisionAction.ANNOTATE),
    # Verified between block(0.82) and flag(0.88) → FLAG (not critical+below block)
    (VerificationStatus.VERIFIED,            0.85, "MEDICAL", ClaimStakes.CRITICAL, DecisionAction.FLAG),
    # Verified below block(0.82) + critical → BLOCK
    (VerificationStatus.VERIFIED,            0.80, "MEDICAL", ClaimStakes.CRITICAL, DecisionAction.BLOCK),
    # Partially supported → always FLAG
    (VerificationStatus.PARTIALLY_SUPPORTED, 0.70, "MEDICAL", ClaimStakes.HIGH,     DecisionAction.FLAG),
    # Contradicted + critical → BLOCK
    (VerificationStatus.CONTRADICTED,        0.05, "MEDICAL", ClaimStakes.CRITICAL, DecisionAction.BLOCK),

    # -- LEGAL domain — block=0.76, flag=0.82 ----------------------------
    # Verified above flag_threshold(0.82) → ANNOTATE
    (VerificationStatus.VERIFIED,            0.90, "LEGAL",   ClaimStakes.HIGH,     DecisionAction.ANNOTATE),
    # Verified below flag_threshold(0.82) → FLAG (high not critical → no block)
    (VerificationStatus.VERIFIED,            0.78, "LEGAL",   ClaimStakes.HIGH,     DecisionAction.FLAG),
    (VerificationStatus.VERIFIED,            0.74, "LEGAL",   ClaimStakes.HIGH,     DecisionAction.FLAG),
    # Verified below block_threshold(0.76) + critical → BLOCK
    (VerificationStatus.VERIFIED,            0.74, "LEGAL",   ClaimStakes.CRITICAL, DecisionAction.BLOCK),
    # Contradicted + high → BLOCK
    (VerificationStatus.CONTRADICTED,        0.20, "LEGAL",   ClaimStakes.HIGH,     DecisionAction.BLOCK),

    # -- FINANCIAL domain — block=0.70, flag=0.76 -------------------------
    # Verified above flag_threshold(0.76) → ANNOTATE
    (VerificationStatus.VERIFIED,            0.80, "FINANCIAL", ClaimStakes.HIGH,   DecisionAction.ANNOTATE),
    # Verified below flag_threshold(0.76) → FLAG (high not critical → no block)
    (VerificationStatus.VERIFIED,            0.73, "FINANCIAL", ClaimStakes.HIGH,   DecisionAction.FLAG),
    (VerificationStatus.VERIFIED,            0.68, "FINANCIAL", ClaimStakes.HIGH,   DecisionAction.FLAG),
    # Unverifiable → always FLAG
    (VerificationStatus.UNVERIFIABLE,        0.30, "FINANCIAL", ClaimStakes.HIGH,   DecisionAction.FLAG),
]


# ---------------------------------------------------------------------------
# Per-case tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,confidence,category,stakes,expected", CASES)
def test_decision_case(status, confidence, category, stakes, expected):
    """Each known-answer case must produce the expected action."""
    actual = _decide(status, confidence, category, stakes)
    assert actual == expected, (
        f"Expected {expected.value} but got {actual.value} for "
        f"status={status.value}, confidence={confidence}, "
        f"category={category}, stakes={stakes.value}"
    )


# ---------------------------------------------------------------------------
# Aggregate precision / recall gate
# ---------------------------------------------------------------------------

def _is_problematic(action: DecisionAction) -> bool:
    """Predicted: the engine raised a concern (flag or block)."""
    return action in (DecisionAction.FLAG, DecisionAction.BLOCK)


def _ground_truth_problematic(
    status: VerificationStatus,
    confidence: float,
    category: str,
    stakes: ClaimStakes,
) -> bool:
    """Ground-truth: should this claim have been flagged or blocked?"""
    from hallucination_middleware.config import get_settings
    s = get_settings()
    block_t = s.domain_block_thresholds.get(category, s.block_threshold)
    flag_t = s.domain_flag_thresholds.get(category, s.flag_threshold)
    if status == VerificationStatus.CONTRADICTED:
        return True
    if status in (VerificationStatus.UNVERIFIABLE, VerificationStatus.PARTIALLY_SUPPORTED):
        return True
    # VERIFIED
    return confidence < flag_t


def test_precision_recall_gate():
    """Aggregate precision and recall over all cases must meet CI thresholds."""
    tp = fp = fn = 0
    for status, confidence, category, stakes, _ in CASES:
        predicted = _is_problematic(_decide(status, confidence, category, stakes))
        truth = _ground_truth_problematic(status, confidence, category, stakes)

        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and truth:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    assert precision >= PRECISION_THRESHOLD, (
        f"Precision {precision:.2f} < threshold {PRECISION_THRESHOLD} "
        f"(tp={tp}, fp={fp})"
    )
    assert recall >= RECALL_THRESHOLD, (
        f"Recall {recall:.2f} < threshold {RECALL_THRESHOLD} "
        f"(tp={tp}, fn={fn})"
    )
