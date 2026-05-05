"""
Domain-specific accuracy gate — MEDICAL, LEGAL, FINANCIAL.

Tests the decision engine against known-answer claims for each domain.
Each domain has strict thresholds (see config.py domain_block_thresholds /
domain_flag_thresholds) that are higher than GENERAL — so the same NLI
confidence that passes in GENERAL will FLAG or BLOCK in MEDICAL/LEGAL.

These tests use the DecisionEngine directly (no LLM/network calls) with
synthetic VerifiedClaim inputs whose confidence values are chosen to fall
precisely in the zones the domain thresholds define.

Domain thresholds (from config.py defaults):
  MEDICAL   block=0.65  flag=0.75
  LEGAL     block=0.60  flag=0.70
  FINANCIAL block=0.58  flag=0.65
  GENERAL   block=0.40  flag=0.55

Benchmark dataset coverage check:
  MEDICAL:   20 claims (10 TRUE, 10 FALSE) — covers pharmacology, anatomy, vaccines
  LEGAL:     12 claims (6 TRUE, 6 FALSE)   — covers GDPR, landmark cases, intl law
  FINANCIAL: 12 claims (6 TRUE, 6 FALSE)   — covers market history, monetary policy
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
from hallucination_middleware.evaluation import (
    MEDICAL_BENCHMARK_CLAIMS,
    LEGAL_BENCHMARK_CLAIMS,
    FINANCIAL_BENCHMARK_CLAIMS,
    ALL_DOMAIN_CLAIMS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_engine = DecisionEngine()


def _make_vc(
    status: str,
    confidence: float,
    domain: str,
    stakes: str = "medium",
    key_evidence: str = "test evidence",
) -> VerifiedClaim:
    claim = ExtractedClaim(
        text="test claim",
        normalized="test claim",
        claim_type=ClaimType.ENTITY,
        stakes=ClaimStakes(stakes),
        span_start=0,
        span_end=10,
        category=domain,
    )
    return VerifiedClaim(
        claim=claim,
        status=VerificationStatus(status),
        confidence=confidence,
        key_evidence=key_evidence,
    )


def _decide(status: str, confidence: float, domain: str, stakes: str = "medium") -> DecisionAction:
    vc = _make_vc(status, confidence, domain, stakes)
    return _engine.decide([vc])[0].action


# ---------------------------------------------------------------------------
# MEDICAL domain threshold tests
# Thresholds: block=0.65, flag=0.75
# ---------------------------------------------------------------------------

class TestMedicalThresholds:
    def test_medical_contradicted_critical_blocks(self):
        """Contradicted + critical stakes MUST block in MEDICAL domain."""
        assert _decide("contradicted", 0.05, "MEDICAL", "critical") == DecisionAction.BLOCK

    def test_medical_verified_above_flag_threshold_annotates(self):
        """Verified at 0.85 (above flag=0.75) → ANNOTATE."""
        assert _decide("verified", 0.85, "MEDICAL") in (DecisionAction.ANNOTATE, DecisionAction.PASS)

    def test_medical_verified_between_block_and_flag_flags(self):
        """Verified at 0.70 — between block(0.65) and flag(0.75) → FLAG."""
        assert _decide("verified", 0.70, "MEDICAL") == DecisionAction.FLAG

    def test_medical_verified_below_block_critical_blocks(self):
        """Verified at 0.60 — below block(0.65) + critical → BLOCK."""
        assert _decide("verified", 0.60, "MEDICAL", "critical") == DecisionAction.BLOCK

    def test_medical_unverifiable_flags(self):
        """Unverifiable medical claims always FLAG — lack of evidence != wrong."""
        assert _decide("unverifiable", 0.30, "MEDICAL") == DecisionAction.FLAG

    def test_medical_partially_supported_flags(self):
        """Partially supported medical claims always FLAG."""
        assert _decide("partially_supported", 0.55, "MEDICAL") == DecisionAction.FLAG

    def test_medical_stricter_than_general(self):
        """
        A VERIFIED claim at 0.65 confidence passes GENERAL (flag=0.55)
        but should FLAG in MEDICAL (flag=0.75).
        """
        general_action = _decide("verified", 0.65, "GENERAL")
        medical_action = _decide("verified", 0.65, "MEDICAL")
        assert general_action in (DecisionAction.ANNOTATE, DecisionAction.PASS)
        assert medical_action == DecisionAction.FLAG

    def test_medical_correct_info_populated_on_contradiction(self):
        """correct_info should be populated from key_evidence when contradicted."""
        evidence = "Aspirin is contraindicated in children under 16 due to Reye syndrome risk."
        vc = _make_vc("contradicted", 0.05, "MEDICAL", "critical", key_evidence=evidence)
        decision = _engine.decide([vc])[0]
        assert decision.correct_info == evidence[:300]
        assert decision.hallucination_type.value == "factual_error"


# ---------------------------------------------------------------------------
# LEGAL domain threshold tests
# Thresholds: block=0.60, flag=0.70
# ---------------------------------------------------------------------------

class TestLegalThresholds:
    def test_legal_contradicted_high_blocks(self):
        """Contradicted + high stakes → BLOCK in LEGAL."""
        assert _decide("contradicted", 0.10, "LEGAL", "high") == DecisionAction.BLOCK

    def test_legal_verified_above_flag_annotates(self):
        """Verified at 0.80 (above flag=0.70) → ANNOTATE."""
        assert _decide("verified", 0.80, "LEGAL") in (DecisionAction.ANNOTATE, DecisionAction.PASS)

    def test_legal_verified_between_thresholds_flags(self):
        """Verified at 0.65 — between block(0.60) and flag(0.70) → FLAG."""
        assert _decide("verified", 0.65, "LEGAL") == DecisionAction.FLAG

    def test_legal_verified_below_block_critical_blocks(self):
        """Verified at 0.55 — below block(0.60) + critical → BLOCK."""
        assert _decide("verified", 0.55, "LEGAL", "critical") == DecisionAction.BLOCK

    def test_legal_unverifiable_flags(self):
        assert _decide("unverifiable", 0.25, "LEGAL") == DecisionAction.FLAG

    def test_legal_stricter_than_general(self):
        """0.62 confidence passes GENERAL but flags LEGAL."""
        assert _decide("verified", 0.62, "GENERAL") in (DecisionAction.ANNOTATE, DecisionAction.PASS)
        assert _decide("verified", 0.62, "LEGAL") == DecisionAction.FLAG


# ---------------------------------------------------------------------------
# FINANCIAL domain threshold tests
# Thresholds: block=0.58, flag=0.65
# ---------------------------------------------------------------------------

class TestFinancialThresholds:
    def test_financial_contradicted_high_blocks(self):
        assert _decide("contradicted", 0.10, "FINANCIAL", "high") == DecisionAction.BLOCK

    def test_financial_verified_above_flag_annotates(self):
        assert _decide("verified", 0.75, "FINANCIAL") in (DecisionAction.ANNOTATE, DecisionAction.PASS)

    def test_financial_verified_between_thresholds_flags(self):
        """Verified at 0.62 — between block(0.58) and flag(0.65) → FLAG."""
        assert _decide("verified", 0.62, "FINANCIAL") == DecisionAction.FLAG

    def test_financial_verified_below_block_critical_blocks(self):
        """Verified at 0.55 — below block(0.58) + critical → BLOCK."""
        assert _decide("verified", 0.55, "FINANCIAL", "critical") == DecisionAction.BLOCK

    def test_financial_partially_supported_flags(self):
        assert _decide("partially_supported", 0.50, "FINANCIAL") == DecisionAction.FLAG


# ---------------------------------------------------------------------------
# Benchmark dataset integrity checks (no pipeline needed)
# ---------------------------------------------------------------------------

class TestBenchmarkDatasetIntegrity:
    def test_medical_dataset_balanced(self):
        """Medical benchmark should have equal TRUE and FALSE claims."""
        true_count  = sum(1 for c in MEDICAL_BENCHMARK_CLAIMS if c.ground_truth)
        false_count = sum(1 for c in MEDICAL_BENCHMARK_CLAIMS if not c.ground_truth)
        assert true_count == false_count, (
            f"Medical benchmark imbalanced: {true_count} TRUE, {false_count} FALSE"
        )

    def test_medical_dataset_minimum_size(self):
        """Medical benchmark should have at least 20 claims."""
        assert len(MEDICAL_BENCHMARK_CLAIMS) >= 20

    def test_legal_dataset_minimum_size(self):
        assert len(LEGAL_BENCHMARK_CLAIMS) >= 10

    def test_financial_dataset_minimum_size(self):
        assert len(FINANCIAL_BENCHMARK_CLAIMS) >= 10

    def test_no_duplicate_claims_in_medical(self):
        texts = [c.text for c in MEDICAL_BENCHMARK_CLAIMS]
        assert len(texts) == len(set(texts)), "Duplicate claim text found in medical benchmark"

    def test_no_duplicate_claims_in_legal(self):
        texts = [c.text for c in LEGAL_BENCHMARK_CLAIMS]
        assert len(texts) == len(set(texts))

    def test_no_duplicate_claims_in_financial(self):
        texts = [c.text for c in FINANCIAL_BENCHMARK_CLAIMS]
        assert len(texts) == len(set(texts))

    def test_all_domain_claims_have_text(self):
        for claim in ALL_DOMAIN_CLAIMS:
            assert claim.text.strip(), "Empty claim text found"
            assert len(claim.text) >= 20, f"Claim too short: '{claim.text}'"

    def test_medical_false_claims_are_dangerous(self):
        """
        Spot-check: the most dangerous medical FALSE claims are present.
        These are claims that could cause patient harm if believed.
        """
        false_texts = " ".join(
            c.text.lower() for c in MEDICAL_BENCHMARK_CLAIMS if not c.ground_truth
        )
        # These specific dangerous misconceptions must be in the benchmark
        assert "aspirin" in false_texts, "Aspirin-child safety claim missing from medical FALSE set"
        assert "antibiotic" in false_texts, "Antibiotics-for-viruses claim missing"
        assert "vaccine" in false_texts or "autism" in false_texts, "Vaccine-autism myth missing"

    def test_legal_gdpr_claims_present(self):
        """GDPR is a critical legal topic — both correct and incorrect claims required."""
        all_legal_texts = " ".join(c.text.lower() for c in LEGAL_BENCHMARK_CLAIMS)
        assert "gdpr" in all_legal_texts, "GDPR not covered in legal benchmark"

    def test_financial_false_claims_cover_common_confusions(self):
        """Common financial confusions (Dow vs S&P, bull vs bear) must be tested."""
        false_texts = " ".join(
            c.text.lower() for c in FINANCIAL_BENCHMARK_CLAIMS if not c.ground_truth
        )
        assert "dow" in false_texts or "500" in false_texts, "Dow/S&P confusion missing"
        assert "bull" in false_texts or "bear" in false_texts, "Bull/bear market confusion missing"


# ---------------------------------------------------------------------------
# Cross-domain precision/recall gate
# Uses synthetic VerifiedClaims to measure that domain thresholds correctly
# separate problematic from good claims in each domain.
# ---------------------------------------------------------------------------

PRECISION_THRESHOLD = 0.85
RECALL_THRESHOLD = 0.80


def _ground_truth_problematic_domain(status: str, confidence: float, domain: str) -> bool:
    s = get_settings()
    block_t = s.domain_block_thresholds.get(domain, s.block_threshold)
    flag_t  = s.domain_flag_thresholds.get(domain,  s.flag_threshold)
    if status in ("contradicted", "unverifiable", "partially_supported"):
        return True
    return confidence < flag_t


# One test case per domain zone — (status, confidence, domain, stakes, expected_action)
DOMAIN_CASES = [
    # MEDICAL
    ("verified",            0.90, "MEDICAL", "medium",   DecisionAction.ANNOTATE),
    ("verified",            0.70, "MEDICAL", "medium",   DecisionAction.FLAG),
    ("verified",            0.60, "MEDICAL", "critical", DecisionAction.BLOCK),
    ("contradicted",        0.05, "MEDICAL", "critical", DecisionAction.BLOCK),
    ("unverifiable",        0.30, "MEDICAL", "high",     DecisionAction.FLAG),
    ("partially_supported", 0.55, "MEDICAL", "medium",   DecisionAction.FLAG),
    # LEGAL
    ("verified",            0.85, "LEGAL",   "medium",   DecisionAction.ANNOTATE),
    ("verified",            0.65, "LEGAL",   "medium",   DecisionAction.FLAG),
    ("verified",            0.55, "LEGAL",   "critical", DecisionAction.BLOCK),
    ("contradicted",        0.10, "LEGAL",   "high",     DecisionAction.BLOCK),
    ("unverifiable",        0.25, "LEGAL",   "medium",   DecisionAction.FLAG),
    # FINANCIAL
    ("verified",            0.80, "FINANCIAL", "medium",   DecisionAction.ANNOTATE),
    ("verified",            0.62, "FINANCIAL", "medium",   DecisionAction.FLAG),
    ("verified",            0.55, "FINANCIAL", "critical", DecisionAction.BLOCK),
    ("contradicted",        0.10, "FINANCIAL", "high",     DecisionAction.BLOCK),
    ("partially_supported", 0.50, "FINANCIAL", "medium",   DecisionAction.FLAG),
]


@pytest.mark.parametrize("status,confidence,domain,stakes,expected", DOMAIN_CASES)
def test_domain_decision_case(status, confidence, domain, stakes, expected):
    """Each domain case must produce the expected DecisionAction."""
    actual = _decide(status, confidence, domain, stakes)
    assert actual == expected, (
        f"[{domain}] Expected {expected.value} but got {actual.value} "
        f"for status={status}, conf={confidence}, stakes={stakes}"
    )


def test_domain_precision_recall_gate():
    """Aggregate precision and recall across all domain cases must meet thresholds."""
    tp = fp = fn = 0
    for status, confidence, domain, stakes, _ in DOMAIN_CASES:
        action  = _decide(status, confidence, domain, stakes)
        pred    = action in (DecisionAction.FLAG, DecisionAction.BLOCK)
        truth   = _ground_truth_problematic_domain(status, confidence, domain)
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    assert precision >= PRECISION_THRESHOLD, (
        f"Domain precision {precision:.2f} < {PRECISION_THRESHOLD} (tp={tp}, fp={fp})"
    )
    assert recall >= RECALL_THRESHOLD, (
        f"Domain recall {recall:.2f} < {RECALL_THRESHOLD} (tp={tp}, fn={fn})"
    )
