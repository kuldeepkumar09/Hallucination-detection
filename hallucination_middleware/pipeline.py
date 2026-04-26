"""
HallucinationDetectionPipeline — central orchestrator connecting every component.

Full data flow:
  text
    → ClaimExtractor     (spaCy + llama-3.1-8b)  extract structured claims
    → Verifier           (BM25 + ChromaDB + reranker + web-RAG + llama-3.3-70b)
    → DecisionEngine     (domain-aware thresholds)
    → AuditTrail         (append-only JSONL)   ← "done" emitted HERE (hot-path end)
    → SelfCorrector      (off hot path — "corrected" SSE event arrives later)
    → HallucinationAudit (returned to caller)

Latency: "done" fires immediately after decisions so SSE clients see results
at ~45 s instead of ~67 s. Self-correction streams in via "corrected" event.
"""
import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

from .audit_trail import AuditTrail
from .cache import ClaimCache
from .claim_extractor import ClaimExtractor
from .config import get_settings
from .corrector import SelfCorrector
from .decision_engine import DecisionEngine
from .engine.hmm_reliability import get_hmm_tracker
from .engine.reward_system import RewardSystem
from .knowledge_base import KnowledgeBase
from .models import HallucinationAudit
from .mpc_controller import MPCController
from .reranker import CrossEncoderReranker
from .verifier import Verifier

logger = logging.getLogger(__name__)


class HallucinationDetectionPipeline:
    """
    Async pipeline — instantiate once at server startup, call
    ``await pipeline.process(text)`` per request. Thread-safe.
    """

    def __init__(self) -> None:
        s = get_settings()

        # --- Knowledge Base (ChromaDB + BM25) ---
        self.knowledge_base = KnowledgeBase()

        # --- Semantic + memory cache ---
        self._cache = ClaimCache(kb_version_fn=lambda: self.knowledge_base.cache_version)

        # --- Cross-encoder reranker (lazy-loaded on first use) ---
        self._reranker = CrossEncoderReranker(s.reranker_model) if s.reranker_enabled else None

        # --- LLM-backed components ---
        self._extractor = ClaimExtractor()
        self._verifier = Verifier(
            knowledge_base=self.knowledge_base,
            cache=self._cache,
            reranker=self._reranker,
        )
        self._decision_engine = DecisionEngine()
        self._corrector = SelfCorrector()

        # --- Optional MPC (off by default) ---
        self._mpc = MPCController(knowledge_base=self.knowledge_base) if s.mpc_enabled else None

        # --- HMM cascade tracker ---
        self._hmm = get_hmm_tracker() if s.hmm_enabled else None

        # --- Reward system ---
        self._reward = RewardSystem(
            alpha=s.reward_alpha,
            beta=s.reward_beta,
            gamma=s.reward_gamma,
            r0=s.reward_r0,
        ) if s.reward_system_enabled else None

        # --- Audit trail ---
        self._audit = AuditTrail()

        # Semaphore limits concurrent pipeline runs to prevent KB/API saturation
        self._sem = asyncio.Semaphore(s.max_workers)

        logger.info(
            "HallucinationDetectionPipeline ready "
            "(workers=%d, cache=%s, reranker=%s, ensemble=%s, "
            "bm25=%s, corrector=%s, mpc=%s, web_rag=%s)",
            s.max_workers,
            "on" if s.cache_enabled else "off",
            "on" if s.reranker_enabled else "off",
            "on" if s.ensemble_for_critical else "off",
            "on" if s.bm25_enabled else "off",
            "on" if s.self_correction_enabled else "off",
            "on" if s.mpc_enabled else "off",
            "on" if s.web_rag_enabled else "off",
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
        progress_cb: Optional[Callable[[str, dict], Coroutine[Any, Any, None]]] = None,
    ) -> HallucinationAudit:
        """
        Run the full detection pipeline on *text*.
        Always returns HallucinationAudit — never raises.
        progress_cb(stage, data) is called at each pipeline stage for SSE streaming.
        "done" is emitted before self-correction; "corrected" follows when ready.
        """
        async with self._sem:
            return await self._run(
                text, model=model, request_id=request_id, progress_cb=progress_cb
            )

    def cache_stats(self) -> dict:
        return self._cache.stats()

    async def invalidate_cache(self) -> None:
        await self._cache.invalidate_all()

    # ------------------------------------------------------------------
    # Internal pipeline — all stages
    # ------------------------------------------------------------------

    async def _run(
        self,
        text: str,
        *,
        model: str = "",
        request_id: Optional[str] = None,
        progress_cb: Optional[Callable[[str, dict], Coroutine[Any, Any, None]]] = None,
    ) -> HallucinationAudit:
        t0 = time.monotonic()
        audit = HallucinationAudit(model=model)
        if request_id:
            audit.request_id = request_id

        async def _emit(stage: str, **data: Any) -> None:
            if progress_cb is not None:
                try:
                    await progress_cb(stage, data)
                except Exception:
                    pass

        try:
            # ── Stage 1: Extract claims ──────────────────────────────────────
            logger.info("[%s] Extracting claims (%d chars) …", audit.request_id, len(text))
            await _emit("extracting", chars=len(text), message="Extracting factual claims…")

            claims = await self._extractor.extract(text)
            logger.info("[%s] Found %d claim(s)", audit.request_id, len(claims))

            if not claims:
                audit.annotated_text = text
                audit.original_text = text
                audit.processing_time_ms = _ms(t0)
                self._audit.log(audit)
                await _emit("done", result=audit.model_dump(mode="json"), message="No factual claims detected.")
                return audit

            await _emit(
                "extracted",
                count=len(claims),
                message=f"Found {len(claims)} claim(s) — verifying against knowledge base…",
            )

            # ── Stage 2: Verify claims ───────────────────────────────────────
            logger.info("[%s] Verifying %d claim(s) …", audit.request_id, len(claims))
            if progress_cb is not None and get_settings().streaming_enabled:
                verified_claims, retrieval_meta = await self._verifier.verify_streaming(claims, progress_cb=progress_cb)
            else:
                verified_claims, retrieval_meta = await self._verifier.verify(claims)
            audit.retrieval_metadata = retrieval_meta

            await _emit(
                "verified",
                count=len(verified_claims),
                message="Verification complete — making decisions…",
            )

            # ── Stage 3: Make decisions ──────────────────────────────────────
            decisions = self._decision_engine.decide(verified_claims)
            audit.claims = decisions

            # ── Stage 4: Annotate + finalise + log ──────────────────────────
            annotated = self._decision_engine.annotate_text(text, decisions)
            audit.annotated_text = annotated

            # ── Stage 4b: HMM cascade detection ─────────────────────────────
            if self._hmm is not None and decisions and len(decisions) >= 4:
                conf_scores = [d.verified_claim.confidence for d in decisions]
                hmm_result = self._hmm.analyze(conf_scores)
                audit.hmm_states = hmm_result["states"]
                audit.hmm_state_labels = hmm_result["state_labels"]
                audit.cascade_point = hmm_result["cascade_point"] if hmm_result["cascade_point"] >= 0 else None
                audit.reliability_score = hmm_result["reliability_score"]
                audit.has_cascade = hmm_result["has_cascade"]
                audit.ttd = hmm_result["ttd"]
                if hmm_result["has_cascade"]:
                    logger.info(
                        "[%s] HMM cascade at claim %d — reliability=%.2f",
                        audit.request_id, hmm_result["cascade_point"],
                        hmm_result["reliability_score"],
                    )

            # ── Stage 4c: Reward system scoring ──────────────────────────────
            if self._reward is not None and decisions:
                conf_scores = [d.verified_claim.confidence for d in decisions]
                statuses = [d.verified_claim.status.value for d in decisions]
                reward_result = self._reward.score_sequence(conf_scores, statuses)
                audit.reward_score = reward_result["total_reward"]
                audit.reward_breakdown = reward_result

            # ── Stage 4d: Reward feedback — escalate decisions ───────────────
            # Claims with strongly negative per-claim reward get escalated.
            # This gives the RARL system real downstream influence.
            if self._reward is not None and decisions and audit.reward_breakdown:
                from .models import DecisionAction  # noqa: PLC0415
                per_claim = audit.reward_breakdown.get("per_claim", [])
                for i, (decision, reward_item) in enumerate(zip(decisions, per_claim)):
                    r = reward_item.get("reward", 0.0)
                    # Skip escalation for unverifiable claims — KB may be sparse, not a contradiction
                    if decision.verified_claim.status.value == "unverifiable":
                        continue
                    # Confident hallucination (reward < -0.5): ANNOTATE → FLAG
                    if r < -0.5 and decision.action == DecisionAction.ANNOTATE:
                        decisions[i] = decision.__class__(
                            verified_claim=decision.verified_claim,
                            action=DecisionAction.FLAG,
                            annotation=decision.annotation + f" [RARL escalated: reward={r:.3f}]",
                        )
                    # Severe penalty (reward < -0.8): FLAG → BLOCK (only for contradicted claims)
                    elif r < -0.8 and decision.action == DecisionAction.FLAG and decision.verified_claim.status.value == "contradicted":
                        decisions[i] = decision.__class__(
                            verified_claim=decision.verified_claim,
                            action=DecisionAction.BLOCK,
                            annotation=decision.annotation + f" [RARL escalated: reward={r:.3f}]",
                        )
                audit.claims = decisions

            audit.finalize(original_text=text, processing_time_ms=_ms(t0))

            cache_hits = sum(1 for m in retrieval_meta if m.cache_hit)
            logger.info(
                "[%s] Hot-path done — %d claims | verified=%d flagged=%d blocked=%d"
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

            # ── Stage 5: Emit "done" BEFORE self-correction ──────────────────
            # SSE clients receive full results at ~45 s; correction arrives later.
            await _emit(
                "done",
                result=audit.model_dump(mode="json"),
                message=(
                    f"Done — {audit.total_claims} claims: "
                    f"{audit.verified_count} verified, "
                    f"{audit.flagged_count} flagged, "
                    f"{audit.blocked_count} blocked."
                ),
            )

            # ── Stage 6: Self-correction (off hot path) ──────────────────────
            # Runs AFTER "done" — "corrected" event arrives incrementally via SSE.
            s = get_settings()
            if s.self_correction_enabled and any(
                d.action.value in ("block", "flag") for d in decisions
            ):
                await _emit("correcting", message="Applying self-correction for flagged claims…")
                try:
                    corrected = await self._corrector.correct(text, decisions)
                    if corrected:
                        audit.corrected_text = corrected
                        logger.info(
                            "[%s] Self-correction applied (%d chars)", audit.request_id, len(corrected)
                        )
                        await _emit(
                            "corrected",
                            corrected_text=corrected,
                            message="Self-correction applied successfully.",
                        )
                except Exception as corr_exc:
                    logger.warning("[%s] Self-correction failed: %s", audit.request_id, corr_exc)

            # ── Stage 7: MPC refinement (optional) ──────────────────────────
            if self._mpc is not None:
                source_for_mpc = audit.corrected_text or text
                await _emit("mpc", message="Running MPC receding-horizon refinement…")
                try:
                    mpc_result = await self._mpc.run(source_for_mpc)
                    if mpc_result.corrected_text != source_for_mpc:
                        audit.corrected_text = mpc_result.corrected_text
                        logger.info(
                            "[%s] MPC refined text (%d chars)", audit.request_id, len(audit.corrected_text)
                        )
                except Exception as mpc_exc:
                    logger.warning("[%s] MPC failed: %s", audit.request_id, mpc_exc)

            self._audit.log(audit)

        except Exception as exc:
            logger.error("[%s] Pipeline error: %s", audit.request_id, exc, exc_info=True)
            audit.annotated_text = text
            audit.original_text = text
            audit.processing_time_ms = _ms(t0)
            self._audit.log(audit)
            await _emit("error", message=f"Pipeline error: {exc}")

        return audit


def _ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000
