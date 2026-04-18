"""
HallucinationDetectionPipeline — orchestrates all middleware components.

Upgrades over v1:
  • ClaimCache + CrossEncoderReranker injected and shared across requests
  • asyncio.Semaphore limits concurrent pipeline executions (max_workers)
  • RetrievalMetadata attached to audit for full retrieval audit trail
  • Cache hit stats logged per request
"""
import asyncio
import logging
import time
from typing import Optional

from .audit_trail import AuditTrail
from .cache import ClaimCache
from .claim_extractor import ClaimExtractor
from .config import get_settings
from .decision_engine import DecisionEngine
from .knowledge_base import KnowledgeBase
from .models import HallucinationAudit
from .reranker import CrossEncoderReranker
from .verifier import Verifier

logger = logging.getLogger(__name__)


class HallucinationDetectionPipeline:
    """
    Async pipeline. Instantiate once at server startup, then call
    ``await pipeline.process(text)`` for each LLM response.
    """

    def __init__(self) -> None:
        s = get_settings()

        self.knowledge_base = KnowledgeBase()
        self._cache = ClaimCache()
        self._reranker = CrossEncoderReranker(s.reranker_model) if s.reranker_enabled else None

        self._extractor = ClaimExtractor()
        self._verifier = Verifier(
            knowledge_base=self.knowledge_base,
            cache=self._cache,
            reranker=self._reranker,
        )
        self._decision_engine = DecisionEngine()
        self._audit = AuditTrail()

        # Limit concurrent pipeline runs to prevent KB / API saturation
        self._sem = asyncio.Semaphore(s.max_workers)

        logger.info(
            "HallucinationDetectionPipeline ready "
            "(workers=%d, cache=%s, reranker=%s, ensemble=%s, bm25=%s)",
            s.max_workers,
            "on" if s.cache_enabled else "off",
            "on" if s.reranker_enabled else "off",
            "on" if s.ensemble_for_critical else "off",
            "on" if s.bm25_enabled else "off",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(
        self,
        text: str,
        *,
        model: str = "",
        request_id: Optional[str] = None,
    ) -> HallucinationAudit:
        """
        Run the full detection pipeline on *text*.
        Always returns a HallucinationAudit — never raises.
        """
        async with self._sem:
            return await self._run(text, model=model, request_id=request_id)

    def cache_stats(self) -> dict:
        return self._cache.stats()

    def invalidate_cache(self) -> None:
        self._cache.invalidate_all()

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _run(
        self,
        text: str,
        *,
        model: str = "",
        request_id: Optional[str] = None,
    ) -> HallucinationAudit:
        t0 = time.monotonic()
        audit = HallucinationAudit(model=model)
        if request_id:
            audit.request_id = request_id

        try:
            # ── 1. Extract claims ──────────────────────────────────────────
            logger.info("[%s] Extracting claims (%d chars) …", audit.request_id, len(text))
            claims = await self._extractor.extract(text)
            logger.info("[%s] Found %d claim(s)", audit.request_id, len(claims))

            if not claims:
                audit.annotated_text = text
                audit.original_text = text
                audit.processing_time_ms = _ms(t0)
                self._audit.log(audit)
                return audit

            # ── 2. Verify claims (returns metadata alongside) ──────────────
            logger.info("[%s] Verifying %d claim(s) …", audit.request_id, len(claims))
            verified_claims, retrieval_meta = await self._verifier.verify(claims)
            audit.retrieval_metadata = retrieval_meta

            # ── 3. Make decisions ──────────────────────────────────────────
            decisions = self._decision_engine.decide(verified_claims)
            audit.claims = decisions

            # ── 4. Build annotated text ────────────────────────────────────
            annotated = self._decision_engine.annotate_text(text, decisions)

            # ── 5. Finalise ────────────────────────────────────────────────
            audit.finalize(original_text=text, processing_time_ms=_ms(t0))
            audit.annotated_text = annotated

            # ── 6. Log ─────────────────────────────────────────────────────
            self._audit.log(audit)

            cache_hits = sum(1 for m in retrieval_meta if m.cache_hit)
            logger.info(
                "[%s] Done — %d claims | %d verified | %d flagged | %d blocked"
                " | confidence=%.2f | cache_hits=%d | %.0fms",
                audit.request_id,
                audit.total_claims,
                audit.verified_count,
                audit.flagged_count,
                audit.blocked_count,
                audit.overall_confidence,
                cache_hits,
                audit.processing_time_ms,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Pipeline error: %s", audit.request_id, exc, exc_info=True)
            audit.annotated_text = text
            audit.original_text = text
            audit.processing_time_ms = _ms(t0)
            self._audit.log(audit)

        return audit


def _ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000
