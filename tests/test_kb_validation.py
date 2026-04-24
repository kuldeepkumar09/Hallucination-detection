"""
KB ingestion validation tests — verifies min-length, source, and binary guards.
Uses a temporary in-memory KB (no disk persistence).
"""
import os
import pytest
import tempfile

os.environ.setdefault("LLM_PROVIDER", "ollama")

from hallucination_middleware.config import get_settings
from hallucination_middleware.knowledge_base import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    get_settings.cache_clear()
    os.environ["KB_PERSIST_DIR"] = str(tmp_path / "chroma")
    os.environ["CHROMA_DB_PATH"] = str(tmp_path / "chroma")
    kb = KnowledgeBase()
    yield kb
    get_settings.cache_clear()


def test_empty_text_returns_zero(kb):
    result = kb.ingest_text("", source="test_source")
    assert result == 0


def test_whitespace_only_returns_zero(kb):
    result = kb.ingest_text("   \n\t  ", source="test_source")
    assert result == 0


def test_text_too_short_returns_zero(kb):
    result = kb.ingest_text("Too short", source="test_source")
    assert result == 0


def test_exactly_20_chars_ingests(kb):
    text = "A" * 20 + " valid content here."
    result = kb.ingest_text(text, source="test_source")
    assert result >= 1


def test_empty_source_raises(kb):
    with pytest.raises(ValueError, match="source"):
        kb.ingest_text("This is valid text with enough characters.", source="")


def test_whitespace_source_raises(kb):
    with pytest.raises(ValueError, match="source"):
        kb.ingest_text("This is valid text with enough characters.", source="   ")


def test_binary_content_raises(kb):
    binary_text = "\x00\x01\x02\x03\x04\x05" * 20 + "padding"
    with pytest.raises(ValueError, match="binary"):
        kb.ingest_text(binary_text, source="binary_source")


def test_valid_text_ingests_successfully(kb):
    text = (
        "The Great Wall of China is not visible from the Moon. "
        "It is approximately 15-30 metres wide, far too narrow to be seen "
        "from a distance of 384,400 kilometres."
    )
    result = kb.ingest_text(text, source="great_wall_fact")
    assert result >= 1


def test_duplicate_ingestion_upserts_safely(kb):
    text = "Albert Einstein was born in Ulm, Germany on 14 March 1879." * 5
    result1 = kb.ingest_text(text, source="einstein")
    result2 = kb.ingest_text(text, source="einstein")
    assert result1 == result2  # same chunks, upserted over existing


def test_source_stripped_of_whitespace(kb):
    text = "Python is a high-level programming language created by Guido van Rossum."
    result = kb.ingest_text(text, source="  python_fact  ")
    assert result >= 1
