"""
Pipeline integration tests.
Tests that don't require an LLM API key are marked with @pytest.mark.no_llm.
Tests that require a live API key are skipped if NVIDIA_NIM_API_KEY or OLLAMA is not set.
"""
import os
import pytest
import asyncio
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_PROVIDER", "ollama")


def _llm_available() -> bool:
    """Return True if a live LLM is reachable."""
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    if provider == "nvidia_nim":
        return bool(os.environ.get("NVIDIA_NIM_API_KEY", "").strip())
    # For ollama, assume available if server is running; skip in CI
    return os.environ.get("CI", "") == ""


# ── Tests that do NOT require LLM ────────────────────────────────────────────

def test_pipeline_imports_cleanly():
    """Pipeline module must import without errors."""
    from hallucination_middleware.pipeline import HallucinationDetectionPipeline
    assert HallucinationDetectionPipeline is not None


def test_audit_trail_imports_cleanly():
    """AuditTrail must import and instantiate without errors."""
    import tempfile
    from hallucination_middleware.audit_trail import AuditTrail
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        trail = AuditTrail(log_path=f.name)
        stats = trail.get_stats()
        assert "total_requests" in stats


def test_config_loads_all_required_fields():
    """Config must expose all fields needed by the pipeline."""
    from hallucination_middleware.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert hasattr(s, "llm_provider")
    assert hasattr(s, "block_threshold")
    assert hasattr(s, "flag_threshold")
    assert hasattr(s, "kb_top_k")
    assert hasattr(s, "reranker_enabled")
    assert hasattr(s, "allowed_origins")


def test_health_endpoint_exposes_streaming_settings():
    from hallucination_middleware.proxy import app
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert 'streaming' in data
        assert isinstance(data['streaming'].get('enabled'), bool)
        assert isinstance(data['streaming'].get('batch_size'), int)
        assert isinstance(data['streaming'].get('claim_delay'), (int, float))


def test_verify_stream_endpoint_requires_text():
    from hallucination_middleware.config import get_settings
    from hallucination_middleware.proxy import app

    settings = get_settings()
    api_key = next(iter(settings.valid_api_keys), None)
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    with TestClient(app) as client:
        response = client.post('/verify/stream', json={}, headers=headers)
        assert response.status_code in (400, 401)
        assert 'text field is required' in response.text or 'Invalid API key' in response.text


def test_decision_engine_annotate_text():
    """annotate_text must return a non-empty string."""
    from hallucination_middleware.decision_engine import DecisionEngine
    from hallucination_middleware.models import (
        ClaimStakes, ClaimType, DecisionAction, ExtractedClaim,
        VerificationStatus, VerifiedClaim, ClaimDecision,
    )
    engine = DecisionEngine()
    claim = ExtractedClaim(
        text="WW2 ended in 1945",
        normalized="World War II ended in 1945",
        claim_type=ClaimType.DATE,
        stakes=ClaimStakes.MEDIUM,
        span_start=0,
        span_end=18,
        category="GENERAL",
    )
    vc = VerifiedClaim(claim=claim, status=VerificationStatus.VERIFIED, confidence=0.92)
    decisions = engine.decide([vc])
    annotated = engine.annotate_text("WW2 ended in 1945", decisions)
    assert isinstance(annotated, str)
    assert len(annotated) > 0


# ── Tests that DO require a live LLM ─────────────────────────────────────────

@pytest.mark.skipif(not _llm_available(), reason="No live LLM available")
@pytest.mark.asyncio
async def test_pipeline_processes_simple_text(tmp_path):
    """End-to-end: pipeline must return a HallucinationAudit with expected fields."""
    os.environ["KB_PERSIST_DIR"] = str(tmp_path / "chroma")
    os.environ["CHROMA_DB_PATH"] = str(tmp_path / "chroma")
    os.environ["AUDIT_LOG_PATH"] = str(tmp_path / "audit.jsonl")

    from hallucination_middleware.config import get_settings
    get_settings.cache_clear()

    from hallucination_middleware.pipeline import HallucinationDetectionPipeline
    pipeline = HallucinationDetectionPipeline()
    audit = await pipeline.process("World War II ended in 1945.")

    assert audit is not None
    assert hasattr(audit, "total_claims")
    assert hasattr(audit, "overall_confidence")
    assert 0.0 <= audit.overall_confidence <= 1.0
