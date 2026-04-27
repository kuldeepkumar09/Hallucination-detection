"""
Decision Engine — maps each VerifiedClaim to an action (PASS / ANNOTATE / FLAG / BLOCK)
and builds the annotated response text.

Decision matrix
---------------
CONTRADICTED + critical or high stakes           → BLOCK
CONTRADICTED + medium or low stakes              → FLAG
UNVERIFIABLE (any stakes)                        → FLAG  (no evidence ≠ wrong; never BLOCK)
confidence < block_threshold + critical stakes   → BLOCK
confidence < flag_threshold                      → FLAG
PARTIALLY_SUPPORTED (any stakes)                 → FLAG
VERIFIED + confidence ≥ flag_threshold           → ANNOTATE (with source) or PASS
"""
import logging
from typing import List, Tuple

from .config import get_settings
from .models import (
    ClaimDecision,
    ClaimStakes,
    ClaimType,
    DecisionAction,
    HallucinationAudit,
    VerificationStatus,
    VerifiedClaim,
)

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Per-claim decision
    # ------------------------------------------------------------------

    def decide(self, verified_claims: List[VerifiedClaim]) -> List[ClaimDecision]:
        """Return one ClaimDecision per VerifiedClaim."""
        decisions: List[ClaimDecision] = []
        for vc in verified_claims:
            action, annotation = self._classify(vc)
            decisions.append(ClaimDecision(
                verified_claim=vc,
                action=action,
                annotation=annotation,
            ))
        return decisions

    def _get_thresholds(self, category: str) -> Tuple[float, float]:
        """Return (block_threshold, flag_threshold) for the given claim category."""
        block = self._settings.domain_block_thresholds.get(
            category, self._settings.block_threshold
        )
        flag = self._settings.domain_flag_thresholds.get(
            category, self._settings.flag_threshold
        )
        return float(block), float(flag)

    _NON_FACTUAL_TYPES = {ClaimType.OPINION, ClaimType.PREDICTION, ClaimType.CREATIVE}

    def _classify(self, vc: VerifiedClaim) -> Tuple[DecisionAction, str]:
        # Non-factual claims are auto-passed — opinions/predictions/creative content
        # cannot be verified against sources and should never be flagged as hallucinations.
        if vc.claim.claim_type in self._NON_FACTUAL_TYPES:
            label = vc.claim.claim_type.value.upper()
            return (DecisionAction.PASS, f"AUTO-PASS ({label}) — not a verifiable factual claim")

        status = vc.status
        confidence = vc.confidence
        stakes = vc.claim.stakes
        category = getattr(vc.claim, "category", "GENERAL")
        is_critical = stakes == ClaimStakes.CRITICAL
        is_high = stakes == ClaimStakes.HIGH

        block_threshold, flag_threshold = self._get_thresholds(category)

        # ---- CONTRADICTED ------------------------------------------------
        # Only CONTRADICTED claims get BLOCK — we have positive evidence they are wrong.
        if status == VerificationStatus.CONTRADICTED:
            reason = vc.contradiction_reason or "Conflicts with authoritative source"
            if is_critical or is_high:
                return (
                    DecisionAction.BLOCK,
                    f"BLOCKED — Contradiction detected ({stakes.value} stakes, {category}): {reason}",
                )
            return (
                DecisionAction.FLAG,
                f"FLAGGED — Contradicted by source (confidence {confidence:.2f}): {reason}",
            )

        # ---- UNVERIFIABLE -------------------------------------------------
        # No evidence found ≠ wrong. Never BLOCK on lack of evidence — only FLAG.
        if status == VerificationStatus.UNVERIFIABLE:
            if is_critical:
                return (
                    DecisionAction.FLAG,
                    f"FLAGGED — Critical {category} claim: no authoritative source found. "
                    "Add relevant documents to the knowledge base to verify.",
                )
            return (
                DecisionAction.FLAG,
                "FLAGGED — Unverifiable: no matching source in knowledge base.",
            )

        # ---- PARTIALLY SUPPORTED -----------------------------------------
        if status == VerificationStatus.PARTIALLY_SUPPORTED:
            return (
                DecisionAction.FLAG,
                (
                    f"FLAGGED — Only partially supported (confidence {confidence:.2f}): "
                    f"{vc.verification_reasoning[:120]}"
                ),
            )

        # ---- VERIFIED — apply domain-specific thresholds ----
        if confidence < block_threshold and is_critical:
            return (
                DecisionAction.BLOCK,
                f"BLOCKED — {category} claim below block threshold {block_threshold:.2f} (confidence {confidence:.2f})",
            )

        if confidence < flag_threshold:
            return (
                DecisionAction.FLAG,
                (
                    f"FLAGGED — Low confidence ({confidence:.2f}, {category} threshold {flag_threshold:.2f}): "
                    f"{vc.verification_reasoning[:120]}"
                ),
            )

        # ---- Fully verified -----------------------------------------------
        if self._settings.annotate_verified:
            sources = ", ".join(d.source for d in vc.supporting_docs[:2]) or "knowledge base"
            return (
                DecisionAction.ANNOTATE,
                f"VERIFIED (confidence {confidence:.2f}, {category}) — Source: {sources}",
            )

        return (DecisionAction.PASS, "")

    # ------------------------------------------------------------------
    # Text annotation
    # ------------------------------------------------------------------

    def annotate_text(self, original_text: str, decisions: List[ClaimDecision]) -> str:
        """Append a compact fact-check summary after the original text."""
        issues = [d for d in decisions if d.action in (DecisionAction.FLAG, DecisionAction.BLOCK)]
        verifications = [d for d in decisions if d.action == DecisionAction.ANNOTATE]

        if not issues and not verifications:
            return original_text

        lines: List[str] = [original_text, "\n\n---\n"]

        for d in issues:
            icon = "✗" if d.action == DecisionAction.BLOCK else "⚠"
            preview = d.verified_claim.claim.text
            if len(preview) > 80:
                preview = preview[:77] + "…"
            reason = d.annotation.split(":", 1)[-1].strip() if ":" in d.annotation else d.annotation
            if len(reason) > 100:
                reason = reason[:97] + "…"
            lines.append(f'{icon} [{d.action.value.upper()}] "{preview}" — {reason}\n')

        if verifications and self._settings.annotate_verified:
            for d in verifications:
                preview = d.verified_claim.claim.text
                if len(preview) > 80:
                    preview = preview[:77] + "…"
                sources = ", ".join(s.source for s in d.verified_claim.supporting_docs[:2]) or "KB"
                lines.append(f'✓ [OK] "{preview}" — {sources}\n')

        return "".join(lines)
