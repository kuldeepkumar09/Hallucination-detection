"""
Shared pytest fixtures for the hallucination detection middleware test suite.

All fixtures that touch the KB use a temporary directory so tests are isolated
and never modify the production ChromaDB.
"""
import os
import tempfile

import pytest

# Override .env settings before importing any middleware modules
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("KB_MIN_RELEVANCE", "0.0")


@pytest.fixture(scope="session")
def tmp_kb_dir():
    """Temporary ChromaDB directory — shared across all tests in a session."""
    with tempfile.TemporaryDirectory(prefix="hallu_test_kb_") as d:
        yield d


@pytest.fixture(scope="session")
def kb(tmp_kb_dir):
    """KnowledgeBase instance backed by a temporary directory."""
    # Patch settings before importing to point at temp dir
    os.environ["KB_PERSIST_DIR"] = tmp_kb_dir
    os.environ["CHROMA_DB_PATH"] = tmp_kb_dir
    os.environ["KB_COLLECTION_NAME"] = "test_docs"

    # Clear lru_cache so env overrides take effect
    from hallucination_middleware.config import get_settings
    get_settings.cache_clear()

    from hallucination_middleware.knowledge_base import KnowledgeBase
    instance = KnowledgeBase()
    yield instance


@pytest.fixture(scope="session")
def populated_kb(kb):
    """KB pre-loaded with a handful of deterministic facts for retrieval tests."""
    kb.ingest_text(
        "World War II ended in 1945. Germany surrendered on 8 May 1945 (V-E Day). "
        "Japan surrendered on 15 August 1945 following the atomic bombings of Hiroshima and Nagasaki.",
        source="ww2_facts",
    )
    kb.ingest_text(
        "The speed of light in a vacuum is approximately 299,792,458 metres per second (≈3×10^8 m/s). "
        "Nothing with mass can travel at or beyond the speed of light.",
        source="physics_facts",
    )
    kb.ingest_text(
        "Aspirin (acetylsalicylic acid) should NOT be given to children under 16 due to the risk of "
        "Reye's syndrome, a rare but potentially fatal condition.",
        source="medical_facts",
    )
    kb.ingest_text(
        "The GDPR (General Data Protection Regulation) entered into force on 25 May 2018. "
        "Violations may result in fines of up to €20 million or 4% of global annual turnover.",
        source="gdpr_facts",
    )
    return kb
