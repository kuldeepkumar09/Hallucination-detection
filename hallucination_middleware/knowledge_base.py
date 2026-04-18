"""
Knowledge Base — ChromaDB vector store + BM25 hybrid search.

Upgrades over v1:
  • Semantic chunking via spaCy (falls back to boundary-aware splitting)
  • BM25 keyword index rebuilt in-memory alongside ChromaDB vectors
  • Hybrid query: weighted fusion of vector + BM25 scores
  • URL ingestion via httpx + BeautifulSoup
  • Document management: list, delete, per-source stats
  • Chunk size / overlap now configurable via Settings
"""
import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Semantic / boundary-aware chunking
# ---------------------------------------------------------------------------

def _try_spacy_sentences(text: str) -> Optional[List[str]]:
    """Return list of sentences from spaCy, or None if spaCy unavailable."""
    try:
        import spacy  # noqa: PLC0415
        try:
            nlp = spacy.load("en_core_web_sm", disable=["ner", "parser", "tagger"])
            nlp.enable_pipe("senter")
        except OSError:
            nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:100_000])   # cap for safety
        return [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    except Exception:  # noqa: BLE001
        return None


def _boundary_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Original boundary-aware chunking (sentence punctuation heuristic)."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            for sep in (". ", ".\n", "! ", "? ", "\n\n", "\n"):
                pos = text.rfind(sep, start + chunk_size // 2, end)
                if pos != -1:
                    end = pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Semantic chunking: group spaCy sentences into chunks ≤ chunk_size chars.
    Falls back to boundary-aware splitting if spaCy is unavailable.
    """
    text = text.strip()
    if not text:
        return []

    sentences = _try_spacy_sentences(text)
    if not sentences:
        return _boundary_split(text, chunk_size, overlap)

    chunks: List[str] = []
    current_parts: List[str] = []
    current_len = 0
    overlap_tail = ""

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len + 1 > chunk_size and current_parts:
            chunk = overlap_tail + " ".join(current_parts)
            chunks.append(chunk.strip())
            # Carry overlap from end of this chunk
            tail = chunk[-overlap:] if len(chunk) > overlap else chunk
            overlap_tail = tail + " "
            current_parts = []
            current_len = 0
        current_parts.append(sent)
        current_len += sent_len + 1

    if current_parts:
        chunks.append((overlap_tail + " ".join(current_parts)).strip())

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# BM25 helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------


class KnowledgeBase:
    """
    Persistent ChromaDB vector store with hybrid BM25+vector search,
    semantic chunking, URL ingestion, and document management.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        persist_dir = self._settings.kb_persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self._chroma = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = self._chroma.get_or_create_collection(
            name=self._settings.kb_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # BM25 in-memory index (rebuilt from ChromaDB on startup)
        self._bm25 = None
        self._bm25_docs: List[Dict] = []   # [{id, source, excerpt}]
        self._rebuild_bm25()

        logger.info(
            "Knowledge base ready — %d chunks, BM25=%s",
            self._col.count(),
            "on" if self._settings.bm25_enabled else "off",
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_text(
        self,
        text: str,
        source: str,
        doc_id: Optional[str] = None,
    ) -> int:
        text = text.strip()
        if not text:
            return 0

        doc_id = doc_id or hashlib.md5(text[:256].encode()).hexdigest()[:12]
        chunks = _chunk_text(
            text,
            self._settings.kb_chunk_size,
            self._settings.kb_chunk_overlap,
        )

        ids, documents, metadatas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(f"{doc_id}__c{i}")
            documents.append(chunk)
            metadatas.append({"source": source, "doc_id": doc_id, "chunk_index": i})

        batch = 100
        for i in range(0, len(ids), batch):
            self._col.upsert(
                ids=ids[i : i + batch],
                documents=documents[i : i + batch],
                metadatas=metadatas[i : i + batch],
            )

        self._rebuild_bm25()
        logger.info("Ingested '%s': %d chunk(s) (doc_id=%s)", source, len(chunks), doc_id)
        return len(chunks)

    def ingest_file(self, file_path: str) -> int:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.suffix.lower() == ".pdf":
            return self._ingest_pdf(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.ingest_text(text, source=path.name)

    def _ingest_pdf(self, path: Path) -> int:
        try:
            from pypdf import PdfReader  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("Install pypdf:  pip install pypdf") from exc
        reader = PdfReader(str(path))
        pages = [p.extract_text() for p in reader.pages if p.extract_text()]
        return self.ingest_text("\n\n".join(pages), source=path.name)

    async def ingest_url(self, url: str, source: Optional[str] = None) -> int:
        """Fetch a URL, strip HTML, and ingest the clean text."""
        try:
            import httpx  # noqa: PLC0415
            from bs4 import BeautifulSoup  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Install httpx and beautifulsoup4:  pip install httpx beautifulsoup4"
            ) from exc

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "HallucinationDetector/1.0"})
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        return self.ingest_text(text, source=source or url)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def query(self, query: str, n_results: int = 5) -> List[Dict]:
        """Pure vector similarity search."""
        total = self._col.count()
        if total == 0:
            return []
        n_results = min(n_results, total)
        results = self._col.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({
                "doc_id": meta.get("doc_id", "unknown"),
                "source": meta.get("source", "unknown"),
                "excerpt": doc,
                "relevance_score": round(max(0.0, 1.0 - dist), 4),
            })
        return hits

    def _bm25_query(self, query: str, n: int) -> List[Dict]:
        """BM25 keyword search over in-memory index."""
        if self._bm25 is None or not self._bm25_docs:
            return []
        tokens = _tokenize(query)
        raw_scores = self._bm25.get_scores(tokens)
        top_indices = sorted(
            range(len(raw_scores)), key=lambda i: raw_scores[i], reverse=True
        )[:n]
        max_score = max((raw_scores[i] for i in top_indices), default=1.0) or 1.0
        hits = []
        for idx in top_indices:
            score = raw_scores[idx]
            if score <= 0:
                continue
            doc = self._bm25_docs[idx]
            hits.append({
                "doc_id": doc["doc_id"],
                "source": doc["source"],
                "excerpt": doc["excerpt"],
                "relevance_score": round(score / max_score, 4),   # normalised to [0,1]
            })
        return hits

    def query_hybrid(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Weighted fusion of vector + BM25 scores.
        score = (1 - bm25_weight) * vector_score + bm25_weight * bm25_score
        """
        s = self._settings
        vector_hits = self.query(query, n_results=n_results * 2)
        bm25_hits = self._bm25_query(query, n=n_results * 2) if s.bm25_enabled else []

        # Merge by excerpt key, accumulate fused scores
        fused: Dict[str, Dict] = {}
        for hit in vector_hits:
            key = hit["excerpt"][:120]
            fused[key] = {**hit, "_vector": hit["relevance_score"], "_bm25": 0.0}
        for hit in bm25_hits:
            key = hit["excerpt"][:120]
            if key in fused:
                fused[key]["_bm25"] = hit["relevance_score"]
            else:
                fused[key] = {**hit, "_vector": 0.0, "_bm25": hit["relevance_score"]}

        w_bm25 = s.bm25_weight if s.bm25_enabled else 0.0
        w_vec = 1.0 - w_bm25
        results = []
        for item in fused.values():
            item["relevance_score"] = round(
                w_vec * item["_vector"] + w_bm25 * item["_bm25"], 4
            )
            item.pop("_vector", None)
            item.pop("_bm25", None)
            results.append(item)

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        # Apply minimum relevance filter
        results = [r for r in results if r["relevance_score"] >= s.kb_min_relevance]
        return results[:n_results]

    async def query_async(self, query: str, n_results: int = 5) -> List[Dict]:
        """Async wrapper — uses hybrid search if BM25 enabled."""
        if self._settings.bm25_enabled:
            return await asyncio.to_thread(self.query_hybrid, query, n_results)
        return await asyncio.to_thread(self.query, query, n_results)

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    def list_documents(self) -> List[Dict]:
        """Return one entry per unique doc_id: {doc_id, source, chunk_count}."""
        total = self._col.count()
        if total == 0:
            return []
        all_meta = self._col.get(include=["metadatas"])["metadatas"]
        seen: Dict[str, Dict] = {}
        for meta in all_meta:
            did = meta.get("doc_id", "unknown")
            if did not in seen:
                seen[did] = {"doc_id": did, "source": meta.get("source", ""), "chunk_count": 0}
            seen[did]["chunk_count"] += 1
        return sorted(seen.values(), key=lambda x: x["source"])

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for doc_id. Returns number of chunks removed."""
        all_data = self._col.get(include=["metadatas"])
        ids_to_delete = [
            id_
            for id_, meta in zip(all_data["ids"], all_data["metadatas"])
            if meta.get("doc_id") == doc_id
        ]
        if ids_to_delete:
            self._col.delete(ids=ids_to_delete)
            self._rebuild_bm25()
            logger.info("Deleted %d chunks for doc_id=%s", len(ids_to_delete), doc_id)
        return len(ids_to_delete)

    def get_document_stats(self) -> Dict:
        """Per-source chunk counts and total."""
        docs = self.list_documents()
        by_source: Dict[str, int] = {}
        for d in docs:
            by_source[d["source"]] = by_source.get(d["source"], 0) + d["chunk_count"]
        return {"total_chunks": self._col.count(), "by_source": by_source}

    def stats(self) -> Dict:
        return {
            "total_chunks": self._col.count(),
            "collection": self._settings.kb_collection_name,
            "persist_dir": self._settings.kb_persist_dir,
            "bm25_enabled": self._settings.bm25_enabled,
            "bm25_indexed": len(self._bm25_docs),
        }

    def clear(self) -> None:
        self._chroma.delete_collection(self._settings.kb_collection_name)
        self._col = self._chroma.get_or_create_collection(
            name=self._settings.kb_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25 = None
        self._bm25_docs = []
        logger.warning("Knowledge base cleared")

    # ------------------------------------------------------------------
    # BM25 index management
    # ------------------------------------------------------------------

    def _rebuild_bm25(self) -> None:
        """Rebuild the in-memory BM25 index from all ChromaDB documents."""
        try:
            from rank_bm25 import BM25Okapi  # noqa: PLC0415
        except ImportError:
            logger.debug("rank-bm25 not installed — BM25 search disabled")
            return

        total = self._col.count()
        if total == 0:
            self._bm25 = None
            self._bm25_docs = []
            return

        all_data = self._col.get(include=["documents", "metadatas"])
        self._bm25_docs = [
            {
                "doc_id": meta.get("doc_id", "unknown"),
                "source": meta.get("source", "unknown"),
                "excerpt": doc,
            }
            for doc, meta in zip(all_data["documents"], all_data["metadatas"])
        ]
        tokenized = [_tokenize(d["excerpt"]) for d in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized)
        logger.debug("BM25 index rebuilt: %d documents", len(self._bm25_docs))
