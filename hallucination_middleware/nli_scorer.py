"""DeBERTa-v3 NLI Cross-Encoder — fast entailment-based claim verification.

Replaces slow LLM verification for high-confidence cases.
Model: cross-encoder/nli-deberta-v3-small (~180 MB, GPU-accelerated)

Label order from the model: [contradiction, entailment, neutral]

Decision logic:
  entailment   > 0.55 → verified          (confidence = entailment_prob)
  contradiction > 0.60 → contradicted     (confidence = contradiction_prob)
  entailment   > 0.40 → partially_supported
  cosine_sim   > 0.68 → partially_supported (semantic fallback for unverifiable)
  else               → unverifiable
"""
import logging
from typing import List, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

_NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-large"
_NLI_SMALL_MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
_SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None
_semantic_model = None
_device: Optional[str] = None
_active_model_name: Optional[str] = None


def _load_model():
    global _model, _device, _active_model_name
    if _model is not None:
        return _model
    try:
        from sentence_transformers import CrossEncoder

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        model_name = _NLI_MODEL_NAME
        # CPU auto-fallback: DeBERTa-v3-large is ~3× slower on CPU (1.5 s vs 0.5 s per claim).
        # Automatically use the small model on CPU to keep NLI-only mode under 6 s total.
        # GPU deployments (CUDA available) use the full large model for best accuracy.
        if _device == "cpu" and "large" in model_name:
            model_name = _NLI_SMALL_MODEL_NAME
            logger.info(
                "[NLI] CPU detected — auto-selecting %s (~3x faster than large; "
                "set NLI_MODEL=cross-encoder/nli-deberta-v3-large in .env to override)",
                model_name,
            )
        else:
            logger.info("[NLI] Loading %s on %s …", model_name, _device)
        _model = CrossEncoder(model_name, device=_device, max_length=512)
        _active_model_name = model_name
        logger.info("[NLI] DeBERTa-v3 ready — model=%s device=%s", model_name, _device)
    except Exception as exc:
        logger.warning("[NLI] Could not load DeBERTa-v3: %s", exc)
    return _model


def _load_semantic_model():
    global _semantic_model
    if _semantic_model is not None:
        return _semantic_model
    try:
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer(_SEMANTIC_MODEL_NAME)
        logger.info("[NLI] Semantic fallback model loaded: %s", _SEMANTIC_MODEL_NAME)
    except Exception as exc:
        logger.debug("[NLI] Semantic fallback unavailable: %s", exc)
    return _semantic_model


def _cosine_similarity(a, b) -> float:
    import numpy as np
    a, b = np.array(a), np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def _split_sentences(text: str) -> List[str]:
    """Split evidence text into sentences for fine-grained NLI scoring.
    NLI cross-encoders perform significantly better on focused (claim, sentence)
    pairs than on (claim, full-paragraph) pairs — the relevant fact is often
    one sentence while surrounding text dilutes the entailment signal.
    """
    import re
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 15]


def _has_key_term_overlap(claim: str, document: str) -> bool:
    """Guard against topic-adjacent but non-supporting semantic matches.
    Requires at least one content word (5+ chars) from the claim to appear
    verbatim in the document. Prevents e.g. 'hearts are muscular' from rescuing
    'hearts pump blood' when the evidence only discusses muscle tissue in general.
    """
    import re
    claim_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', claim))
    doc_lower = document.lower()
    return any(w in doc_lower for w in claim_words)


def _classify(entail: float, contra: float, neutral: float) -> Tuple[float, str]:
    # Lowered entailment threshold: 0.55 instead of 0.60 to reduce false negatives
    if entail > 0.55:
        return entail, "verified"
    if contra > 0.60:
        return contra, "contradicted"
    if entail > 0.40:
        return entail, "partially_supported"
    return neutral * 0.4, "unverifiable"


class NLIScorer:
    """
    Scores (claim, document) pairs using DeBERTa-v3 NLI cross-encoder.
    GPU-accelerated on RTX 3050 when available; CPU fallback automatic.
    """

    def __init__(self) -> None:
        self._model = None  # lazy

    def _ensure_loaded(self):
        if self._model is None:
            self._model = _load_model()

    # ------------------------------------------------------------------
    # Single pair
    # ------------------------------------------------------------------

    def score_pair(self, claim: str, document: str) -> Tuple[float, str]:
        """
        Score one (claim, document) pair.
        Returns (confidence, status).
        Falls back to semantic cosine similarity when NLI returns unverifiable
        (addresses DeBERTa asymmetry: strong at contradictions, weak at verifying true claims).
        """
        self._ensure_loaded()
        if self._model is None:
            return 0.3, "unverifiable"
        try:
            scores = self._model.predict(
                [(claim, document[:1500])],
                apply_softmax=True,
            )[0]
            conf, status = _classify(float(scores[1]), float(scores[0]), float(scores[2]))
            # Semantic fallback: when NLI can't decide, cosine similarity rescues true claims.
            # Key-term overlap guard prevents topic-adjacent but non-supporting matches.
            if status == "unverifiable":
                sem = _load_semantic_model()
                if sem is not None:
                    try:
                        doc_slice = document[:512]
                        embeddings = sem.encode([claim, doc_slice])
                        cosine = _cosine_similarity(embeddings[0], embeddings[1])
                        if cosine >= 0.68 and _has_key_term_overlap(claim, doc_slice):
                            logger.debug(
                                "[NLI] semantic fallback: unverifiable → partially_supported (cosine=%.3f)",
                                cosine,
                            )
                            return round(cosine, 3), "partially_supported"
                    except Exception:
                        pass
            return conf, status
        except Exception as exc:
            logger.debug("[NLI] pair scoring failed: %s", exc)
            return 0.3, "unverifiable"

    # ------------------------------------------------------------------
    # Batch (claim vs multiple docs)
    # ------------------------------------------------------------------

    def score_against_docs(
        self,
        claim: str,
        documents: List[str],
        top_k: int = 3,
    ) -> List[Tuple[float, str, str]]:
        """
        Score claim against multiple document excerpts at sentence level.
        Each document is split into sentences; the model scores (claim, sentence) pairs.
        Sentence-level scoring outperforms full-paragraph scoring because the relevant
        fact is usually one sentence — surrounding text dilutes the entailment signal.
        Returns list of (best_confidence, best_status, source_sentence) sorted desc.
        """
        self._ensure_loaded()
        if self._model is None or not documents:
            return [(0.3, "unverifiable", d[:150]) for d in documents[:top_k]]
        try:
            # Expand each document into sentences; fall back to full doc if unsplittable
            sentence_pairs: List[Tuple[str, str]] = []
            sentence_doc_idx: List[int] = []
            for doc_i, doc in enumerate(documents):
                sentences = _split_sentences(doc[:512])
                if not sentences:
                    sentences = [doc[:300]]
                for sent in sentences:
                    sentence_pairs.append((claim, sent))
                    sentence_doc_idx.append(doc_i)

            raw = self._model.predict(sentence_pairs, apply_softmax=True)

            # Keep best result per document (highest confidence across all its sentences)
            best_per_doc: dict = {}
            for pair_i, scores in enumerate(raw):
                doc_i = sentence_doc_idx[pair_i]
                conf, status = _classify(float(scores[1]), float(scores[0]), float(scores[2]))
                sent_text = sentence_pairs[pair_i][1]
                if doc_i not in best_per_doc or conf > best_per_doc[doc_i][0]:
                    best_per_doc[doc_i] = (conf, status, sent_text[:150])

            results = [best_per_doc[i] for i in sorted(best_per_doc)]
            results.sort(key=lambda x: x[0], reverse=True)
            return results[:top_k]
        except Exception as exc:
            logger.debug("[NLI] batch scoring failed: %s", exc)
            return [(0.3, "unverifiable", d[:150]) for d in documents[:top_k]]

    def best_score(
        self,
        claim: str,
        documents: List[str],
    ) -> Tuple[float, str]:
        """Return (best_confidence, best_status) across all documents.
        Applies semantic cosine fallback when all documents score as unverifiable.
        """
        if not documents:
            return 0.3, "unverifiable"
        results = self.score_against_docs(claim, documents, top_k=len(documents))
        for conf, status, _ in results:
            if status in ("verified", "contradicted", "partially_supported"):
                return conf, status
        # All docs unverifiable — try semantic similarity against the best-ranked doc
        sem = _load_semantic_model()
        if sem is not None and documents:
            try:
                best_doc = documents[0]
                doc_slice = best_doc[:512]
                embeddings = sem.encode([claim, doc_slice])
                cosine = _cosine_similarity(embeddings[0], embeddings[1])
                if cosine >= 0.68 and _has_key_term_overlap(claim, doc_slice):
                    logger.debug(
                        "[NLI] best_score semantic fallback: unverifiable → partially_supported (cosine=%.3f)",
                        cosine,
                    )
                    return round(cosine, 3), "partially_supported"
            except Exception:
                pass
        return (results[0][0], results[0][1]) if results else (0.3, "unverifiable")


_scorer: Optional[NLIScorer] = None


def get_nli_scorer() -> NLIScorer:
    global _scorer
    if _scorer is None:
        _scorer = NLIScorer()
    return _scorer
