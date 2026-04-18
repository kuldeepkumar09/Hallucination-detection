"""
Decision Engine — maps each VerifiedClaim to an action (PASS / ANNOTATE / FLAG / BLOCK)
and builds the annotated response text.

Decision matrix
---------------
CONTRADICTED + critical or high stakes           → BLOCK
CONTRADICTED + medium or low stakes              → FLAG
UNVERIFIABLE + critical stakes                   → BLOCK  (cannot take the risk)
UNVERIFIABLE + high / medium / low stakes        → FLAG
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

    def _classify(self, vc: VerifiedClaim) -> Tuple[DecisionAction, str]:
        status = vc.status
        confidence = vc.confidence
        stakes = vc.claim.stakes
        is_critical = stakes == ClaimStakes.CRITICAL
        is_high = stakes == ClaimStakes.HIGH

        # ---- CONTRADICTED ------------------------------------------------
        if status == VerificationStatus.CONTRADICTED:
            reason = vc.contradiction_reason or "Conflicts with authoritative source"
            if is_critical or is_high:
                return (
                    DecisionAction.BLOCK,
                    f"BLOCKED — Contradiction detected ({stakes.value} stakes): {reason}",
                )
            return (
                DecisionAction.FLAG,
                f"FLAGGED — Contradicted by source (confidence {confidence:.2f}): {reason}",
            )

        # ---- UNVERIFIABLE -------------------------------------------------
        if status == VerificationStatus.UNVERIFIABLE:
            if is_critical:
                return (
                    DecisionAction.BLOCK,
                    "BLOCKED — Critical claim that cannot be verified against any authoritative source",
                )
            return (
                DecisionAction.FLAG,
                "FLAGGED — Unverifiable: no authoritative source found for this claim",
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

        # ---- VERIFIED — check confidence thresholds ----------------------
        if confidence < self._settings.block_threshold and is_critical:
            return (
                DecisionAction.BLOCK,
                f"BLOCKED — Critical claim with very low verification confidence ({confidence:.2f})",
            )

        if confidence < self._settings.flag_threshold:
            return (
                DecisionAction.FLAG,
                (
                    f"FLAGGED — Low confidence ({confidence:.2f}): "
                    f"{vc.verification_reasoning[:120]}"
                ),
            )

        # ---- Fully verified -----------------------------------------------
        if self._settings.annotate_verified:
            sources = ", ".join(d.source for d in vc.supporting_docs[:2]) or "knowledge base"
            return (
                DecisionAction.ANNOTATE,
                f"VERIFIED (confidence {confidence:.2f}) — Source: {sources}",
            )

        return (DecisionAction.PASS, "")

    # ------------------------------------------------------------------
    # Text annotation
    # ------------------------------------------------------------------

    def annotate_text(self, original_text: str, decisions: List[ClaimDecision]) -> str:
        """
        Append a structured Hallucination Detection Report section to the
        response text.  The original text is never modified inline — this
        keeps it readable while providing a full audit trail.
        """
        issues = [d for d in decisions if d.action in (DecisionAction.FLAG, DecisionAction.BLOCK)]
        verifications = [d for d in decisions if d.action == DecisionAction.ANNOTATE]

        if not issues and not verifications:
            return original_text

        lines: List[str] = [original_text, "\n\n---\n## Hallucination Detection Report\n"]

        if issues:
            lines.append("### [!] Issues\n")
            for d in issues:
                icon = "[BLOCK]" if d.action == DecisionAction.BLOCK else "[FLAG]"
                preview = d.verified_claim.claim.text
                if len(preview) > 70:
                    preview = preview[:67] + "..."
                lines.append(f'{icon} **[{d.action.value.upper()}]** "{preview}"\n')
                lines.append(f"   -> {d.annotation}\n\n")

        if verifications and self._settings.annotate_verified:
            lines.append("### [OK] Verified Claims\n")
            for d in verifications:
                preview = d.verified_claim.claim.text
                if len(preview) > 70:
                    preview = preview[:67] + "..."
                lines.append(f'[OK] "{preview}"\n')
                lines.append(f"   -> {d.annotation}\n\n")

        return "".join(lines)
