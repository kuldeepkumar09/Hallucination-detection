"""
SelfCorrector tests — patch the LLM client to avoid real API calls.
"""
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("LLM_PROVIDER", "ollama")

from hallucination_middleware.corrector import SelfCorrector
from hallucination_middleware.models import (
    ClaimDecision, ClaimType, ClaimStakes, DecisionAction,
    ExtractedClaim, VerificationStatus, VerifiedClaim,
)


def _make_decision(action: DecisionAction, claim_text="The sky is green") -> ClaimDecision:
    claim = ExtractedClaim(
        text=claim_text,
        normalized=claim_text,
        claim_type=ClaimType.ENTITY,
        stakes=ClaimStakes.MEDIUM,
        span_start=0,
        span_end=len(claim_text),
    )
    vc = VerifiedClaim(
        claim=claim,
        status=VerificationStatus.CONTRADICTED,
        confidence=0.1,
        verification_reasoning="Source states sky is blue",
        key_evidence="The sky is blue",
        contradiction_reason="Sky is actually blue, not green",
    )
    return ClaimDecision(verified_claim=vc, action=action, annotation="FLAGGED")


@pytest.fixture
def corrector():
    return SelfCorrector()


@pytest.mark.asyncio
async def test_correct_returns_none_when_disabled(corrector):
    corrector._enabled = False
    decisions = [_make_decision(DecisionAction.FLAG)]
    result = await corrector.correct("Some text", decisions)
    assert result is None


@pytest.mark.asyncio
async def test_correct_returns_none_when_no_issues(corrector):
    decisions = [_make_decision(DecisionAction.PASS)]
    result = await corrector.correct("Some text", decisions)
    assert result is None


@pytest.mark.asyncio
async def test_correct_calls_llm_for_flagged(corrector):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "The sky is blue."

    with patch.object(corrector._client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        decisions = [_make_decision(DecisionAction.FLAG)]
        result = await corrector.correct("The sky is green.", decisions)

    assert result == "The sky is blue."


@pytest.mark.asyncio
async def test_correct_calls_llm_for_blocked(corrector):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Corrected text here."

    with patch.object(corrector._client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        decisions = [_make_decision(DecisionAction.BLOCK)]
        result = await corrector.correct("Original text.", decisions)

    assert result == "Corrected text here."


@pytest.mark.asyncio
async def test_correct_retries_on_empty_response(corrector):
    empty = MagicMock()
    empty.choices = [MagicMock()]
    empty.choices[0].message.content = ""

    good = MagicMock()
    good.choices = [MagicMock()]
    good.choices[0].message.content = "Fixed text."

    call_count = 0

    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return empty if call_count < 2 else good

    with patch.object(corrector._client.chat.completions, "create", new=mock_create):
        decisions = [_make_decision(DecisionAction.FLAG)]
        result = await corrector.correct("Original.", decisions)

    assert result == "Fixed text."
    assert call_count == 2


@pytest.mark.asyncio
async def test_correct_returns_none_on_all_failures(corrector):
    async def always_raise(**kwargs):
        raise Exception("LLM unavailable")

    with patch.object(corrector._client.chat.completions, "create", new=always_raise):
        decisions = [_make_decision(DecisionAction.FLAG)]
        result = await corrector.correct("Original.", decisions)

    assert result is None


def test_build_corrections_includes_evidence(corrector):
    d = _make_decision(DecisionAction.FLAG)
    items = corrector._build_corrections([d])
    assert len(items) == 1
    assert "sky is green" in items[0].lower() or "sky" in items[0].lower()
    assert "blue" in items[0]
