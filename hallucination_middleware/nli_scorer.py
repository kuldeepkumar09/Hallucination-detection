"""DeBERTa-v3 NLI Cross-Encoder — fast entailment-based claim verification.

Replaces slow LLM verification for high-confidence cases.
Model: cross-encoder/nli-deberta-v3-small (~180 MB, GPU-accelerated)

Label order from the model: [contradiction, entailment, neutral]

Decision logic:
  entailment   > 0.60 → verified          (confidence = entailment_prob)
  contradiction > 0.60 → contradicted     (confidence = contradiction_prob)
  entailment   > 0.40 → partially_supported
  else               → unverifiable
"""
import logging
from typing import List, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

_NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
_model = None
_device: Optional[str] = None


def _load_model():
    global _model, _device
    if _model is not None:
        return _model
    try:
        from sentence_transformers import CrossEncoder

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[NLI] Loading %s on %s …", _NLI_MODEL_NAME, _device)
        _model = CrossEncoder(_NLI_MODEL_NAME, device=_device, max_length=512)
        logger.info("[NLI] DeBERTa-v3 ready on %s", _device)
    except Exception as exc:
        logger.warning("[NLI] Could not load DeBERTa-v3: %s", exc)
    return _model


def _classify(entail: float, contra: float, neutral: float) -> Tuple[float, str]:
    if entail > 0.60:
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
        """
        self._ensure_loaded()
        if self._model is None:
            return 0.3, "unverifiable"
        try:
            scores = self._model.predict(
                [(claim, document[:1500])],
                apply_softmax=True,
            )[0]
            return _classify(float(scores[1]), float(scores[0]), float(scores[2]))
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
        Score claim against multiple document excerpts.
        Returns list of (confidence, status, doc_excerpt) sorted by confidence desc.
        """
        self._ensure_loaded()
        if self._model is None or not documents:
            return [(0.3, "unverifiable", d[:150]) for d in documents[:top_k]]
        try:
            pairs = [(claim, doc[:512]) for doc in documents]
            raw = self._model.predict(pairs, apply_softmax=True)
            results = []
            for i, scores in enumerate(raw):
                conf, status = _classify(float(scores[1]), float(scores[0]), float(scores[2]))
                results.append((conf, status, documents[i][:150]))
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
        """Return (best_confidence, best_status) across all documents."""
        if not documents:
            return 0.3, "unverifiable"
        results = self.score_against_docs(claim, documents, top_k=len(documents))
        for conf, status, _ in results:
            if status in ("verified", "contradicted", "partially_supported"):
                return conf, status
        return (results[0][0], results[0][1]) if results else (0.3, "unverifiable")


_scorer: Optional[NLIScorer] = None


def get_nli_scorer() -> NLIScorer:
    global _scorer
    if _scorer is None:
        _scorer = NLIScorer()
    return _scorer
