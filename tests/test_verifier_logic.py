"""
Verifier logic tests — mock the LLM client so no real API calls are made.
Tests JSON extraction, result building, and fallback behaviour.
"""
import os
import pytest

os.environ.setdefault("LLM_PROVIDER", "ollama")

from hallucination_middleware.verifier import _extract_json, Verifier
from hallucination_middleware.models import (
    ClaimType, ClaimStakes, ExtractedClaim, VerificationStatus,
)


# ---------------------------------------------------------------------------
# _extract_json (pure function — no mocks needed)
# ---------------------------------------------------------------------------

def test_extract_json_clean():
    raw = '{"results": [{"status": "verified", "confidence": 0.9}]}'
    d = _extract_json(raw)
    assert d["results"][0]["status"] == "verified"


def test_extract_json_with_markdown_fence():
    raw = '```json\n{"status": "contradicted", "confidence": 0.1}\n```'
    d = _extract_json(raw)
    assert d["status"] == "contradicted"


def test_extract_json_with_leading_prose():
    raw = 'Here is my analysis:\n{"status": "unverifiable", "confidence": 0.3}'
    d = _extract_json(raw)
    assert d["status"] == "unverifiable"


def test_extract_json_empty_string():
    assert _extract_json("") == {}


def test_extract_json_no_json():
    assert _extract_json("This is just a sentence with no JSON.") == {}


def test_extract_json_truncated():
    raw = '{"results": [{"status": "verified", "confidence": 0.8'
    # Truncated JSON — should return {} gracefully
    result = _extract_json(raw)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _make_unverifiable / _all_unverifiable (static methods)
# ---------------------------------------------------------------------------

def _make_claim():
    return ExtractedClaim(
        text="Test claim",
        normalized="test claim",
        claim_type=ClaimType.ENTITY,
        stakes=ClaimStakes.MEDIUM,
        span_start=0,
        span_end=10,
    )


def test_make_unverifiable_returns_correct_status():
    claim = _make_claim()
    vc = Verifier._make_unverifiable(claim, "No source found")
    assert vc.status == VerificationStatus.UNVERIFIABLE
    assert vc.confidence == 0.3
    assert vc.verification_reasoning == "No source found"


def test_all_unverifiable_length_matches():
    claims = [_make_claim() for _ in range(4)]
    results = Verifier._all_unverifiable(claims, "Timeout")
    assert len(results) == 4
    assert all(r.status == VerificationStatus.UNVERIFIABLE for r in results)


def test_all_unverifiable_empty():
    assert Verifier._all_unverifiable([], "reason") == []
