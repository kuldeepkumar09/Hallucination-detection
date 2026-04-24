"""
Cross-encoder re-ranker for retrieved documents.

Uses sentence-transformers CrossEncoder (ms-marco-MiniLM-L-6-v2 by default)
to score (query, document) pairs and return the top-k most relevant documents.

Lazy-loads the model on first use to avoid startup penalty.
Degrades gracefully: if sentence-transformers is not installed, returns
the input documents unchanged with a one-time warning log.
"""
import asyncio
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_UNAVAILABLE_WARNED = False


class CrossEncoderReranker:
    """
    Synchronous cross-encoder re-ranker with an async wrapper.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier for the CrossEncoder.
        Default: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model = None          # lazy-loaded
        self._available: Optional[bool] = None  # None = not yet checked
        self._lock = threading.Lock()           # prevent concurrent load race

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 3,
    ) -> List[Dict]:
        """
        Score each (query, doc['excerpt']) pair and return the top-k docs
        sorted by relevance, highest first.

        Adds a ``rerank_score`` field to each returned dict.
        Returns the input list unchanged if the model is unavailable.
        """
        if not documents:
            return documents

        model = self._load_model()
        if model is None:
            return documents[:top_k]

        pairs = [(query, doc.get("excerpt", "")[:512]) for doc in documents]
        try:
            scores = model.predict(pairs, show_progress_bar=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cross-encoder prediction failed: %s", exc)
            return documents[:top_k]

        scored = [
            {**doc, "rerank_score": float(score)}
            for doc, score in zip(documents, scores)
        ]
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]

    async def rerank_async(
        self,
        query: str,
        documents: List[Dict],
        top_k: int = 3,
    ) -> List[Dict]:
        """Non-blocking wrapper — runs re-ranking in a thread pool."""
        return await asyncio.to_thread(self.rerank, query, documents, top_k)

    def is_available(self) -> bool:
        """Return True if sentence-transformers is installed and model is loadable."""
        return self._load_model() is not None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_model(self):
        global _UNAVAILABLE_WARNED

        # Fast path — no lock needed for reads after init
        if self._available is False:
            return None
        if self._model is not None:
            return self._model

        # Slow path — acquire lock so only one thread loads the model
        with self._lock:
            if self._available is False:
                return None
            if self._model is not None:
                return self._model

            # Load inside the lock so other threads wait here
            try:
                import torch  # noqa: PLC0415
                from sentence_transformers import CrossEncoder  # noqa: PLC0415
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info("Loading cross-encoder model: %s on %s …", self._model_name, device)
                self._model = CrossEncoder(self._model_name, device=device)
                self._available = True
                logger.info("Cross-encoder ready on %s", device)
            except ImportError:
                if not _UNAVAILABLE_WARNED:
                    logger.warning(
                        "sentence-transformers not installed — re-ranking disabled. "
                        "Install with:  pip install sentence-transformers"
                    )
                    _UNAVAILABLE_WARNED = True
                self._available = False
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load cross-encoder (%s): %s", self._model_name, exc)
                self._available = False

        return self._model
