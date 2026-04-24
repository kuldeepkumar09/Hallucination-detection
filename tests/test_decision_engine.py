"""
DecisionEngine tests — pure Python, no LLM or KB calls.
Builds VerifiedClaim objects directly and asserts correct PASS/ANNOTATE/FLAG/BLOCK decisions.
"""
import os
import pytest

os.environ.setdefault("LLM_PROVIDER", "ollama")

from hallucination_middleware.config import get_settings
from hallucination_middleware.decision_engine import DecisionEngine
from hallucination_middleware.models import (
    ClaimStakes,
    ClaimType,
    DecisionAction,
    ExtractedClaim,
    VerificationStatus,
    VerifiedClaim,
)


def _make_claim(stakes: str = "medium", category: str = "GENERAL") -> ExtractedClaim:
    return ExtractedClaim(
        text="Test claim",
        normalized="test claim",
        claim_type=ClaimType.ENTITY,
        stakes=ClaimStakes(stakes),
        span_start=0,
        span_end=10,
        category=category,
    )


def _make_vc(
    status: str,
    confidence: float,
    stakes: str = "medium",
    category: str = "GENERAL",
) -> VerifiedClaim:
    claim = _make_claim(stakes=stakes, category=category)
    return VerifiedClaim(
        claim=claim,
        status=VerificationStatus(status),
        confidence=confidence,
    )


@pytest.fixture
def engine():
    get_settings.cache_clear()
    return DecisionEngine()


def test_verified_high_confidence_annotates(engine):
    vc = _make_vc("verified", 0.92)
    decisions = engine.decide([vc])
    assert decisions[0].action in (DecisionAction.ANNOTATE, DecisionAction.PASS)


def test_contradicted_critical_blocks(engine):
    vc = _make_vc("contradicted", 0.1, stakes="critical")
    decisions = engine.decide([vc])
    assert decisions[0].action == DecisionAction.BLOCK


def test_contradicted_medium_flags(engine):
    vc = _make_vc("contradicted", 0.1, stakes="medium")
    decisions = engine.decide([vc])
    assert decisions[0].action == DecisionAction.FLAG


def test_unverifiable_critical_flags(engine):
    """Unverifiable claims are always FLAGGED — never BLOCKED. Lack of evidence ≠ wrong."""
    vc = _make_vc("unverifiable", 0.25, stakes="critical")
    decisions = engine.decide([vc])
    assert decisions[0].action == DecisionAction.FLAG


def test_unverifiable_low_stakes_flags(engine):
    vc = _make_vc("unverifiable", 0.25, stakes="low")
    decisions = engine.decide([vc])
    assert decisions[0].action == DecisionAction.FLAG


def test_partially_supported_flags(engine):
    vc = _make_vc("partially_supported", 0.55, stakes="medium")
    decisions = engine.decide([vc])
    assert decisions[0].action == DecisionAction.FLAG


def test_medical_domain_strict_threshold(engine):
    """MEDICAL domain has block_threshold=0.82 — a 0.80-confidence verified claim should flag."""
    vc = _make_vc("verified", 0.80, stakes="medium", category="MEDICAL")
    decisions = engine.decide([vc])
    # Medical threshold is strict — 0.80 is below the 0.82 block threshold
    assert decisions[0].action in (DecisionAction.FLAG, DecisionAction.BLOCK)


def test_empty_claims_returns_empty(engine):
    decisions = engine.decide([])
    assert decisions == []
