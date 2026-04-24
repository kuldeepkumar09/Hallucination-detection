"""
Knowledge Base tests — no LLM calls required.
All tests use the populated_kb fixture from conftest.py.
"""
import pytest


def test_kb_ingest_returns_chunk_count(populated_kb):
    """Ingesting text should return a positive chunk count."""
    chunks = populated_kb.ingest_text("The Earth orbits the Sun.", source="test_fact")
    assert chunks >= 1


def test_kb_vector_query_returns_hits(populated_kb):
    """A relevant query should return at least one result."""
    hits = populated_kb.query("World War II end date", n_results=3)
    assert len(hits) >= 1


def test_kb_query_relevance_score_in_range(populated_kb):
    """All returned hits must have relevance scores in [0, 1]."""
    hits = populated_kb.query("speed of light", n_results=5)
    for h in hits:
        assert 0.0 <= h["relevance_score"] <= 1.0, f"Bad score: {h['relevance_score']}"


def test_kb_hybrid_query_returns_results(populated_kb):
    """Hybrid BM25+vector search should return results for a known fact."""
    hits = populated_kb.query_hybrid("aspirin children Reye syndrome", n_results=5)
    assert len(hits) >= 1
    assert any("aspirin" in h["excerpt"].lower() or "reye" in h["excerpt"].lower() for h in hits)


def test_kb_list_documents_includes_ingested_source(populated_kb):
    """list_documents() should include every source we ingested."""
    docs = populated_kb.list_documents()
    sources = {d["source"] for d in docs}
    assert "ww2_facts" in sources
    assert "physics_facts" in sources


def test_kb_stats_total_chunks_positive(populated_kb):
    """stats() should report a positive total_chunks count."""
    stats = populated_kb.stats()
    assert stats["total_chunks"] > 0


def test_kb_delete_removes_document(kb):
    """Deleting a document should reduce the chunk count."""
    before = kb._col.count()
    kb.ingest_text("Temporary test content for deletion.", source="delete_me")
    docs = kb.list_documents()
    doc_id = next((d["doc_id"] for d in docs if d["source"] == "delete_me"), None)
    assert doc_id is not None
    deleted = kb.delete_document(doc_id)
    assert deleted >= 1
    assert kb._col.count() == before
