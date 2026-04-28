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
import re
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
    # Cross-claim consistency check
    # ------------------------------------------------------------------

    _DATE_RE = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')

    def check_internal_contradictions(self, decisions: List[ClaimDecision]) -> List[ClaimDecision]:
        """
        Detect claims within the same response that contradict each other on dates/years.
        If two PASS/ANNOTATE claims reference the same subject entity but different years,
        escalate the lower-confidence one to FLAG with an internal-contradiction annotation.
        Only escalates — never downgrade already-flagged/blocked decisions.
        """
        # Collect only passable decisions (not already flagged/blocked)
        escalatable = [
            (i, d) for i, d in enumerate(decisions)
            if d.action in (DecisionAction.PASS, DecisionAction.ANNOTATE)
        ]
        if len(escalatable) < 2:
            return decisions

        updated = list(decisions)
        # Extract (subject_words, years) per decision for pairwise comparison
        parsed = []
        for i, d in escalatable:
            text = d.verified_claim.claim.text
            years = self._DATE_RE.findall(text)
            # Subject heuristic: capitalized words (proper nouns) in the claim
            subjects = set(re.findall(r'\b[A-Z][a-z]{2,}\b', text))
            parsed.append((i, d, subjects, set(years)))

        for a_idx in range(len(parsed)):
            for b_idx in range(a_idx + 1, len(parsed)):
                i_a, d_a, subj_a, years_a = parsed[a_idx]
                i_b, d_b, subj_b, years_b = parsed[b_idx]

                # Only flag if same subject AND conflicting years
                if not (subj_a & subj_b):
                    continue
                if not years_a or not years_b:
                    continue
                if years_a == years_b:
                    continue

                # Escalate the lower-confidence claim (or second if equal)
                conf_a = d_a.verified_claim.confidence
                conf_b = d_b.verified_claim.confidence
                target_i = i_a if conf_a <= conf_b else i_b
                target_d = updated[target_i]

                shared = ", ".join(sorted(subj_a & subj_b))
                annotation = (
                    f"FLAGGED — Internal contradiction: '{shared}' has conflicting "
                    f"dates/years across claims ({sorted(years_a)} vs {sorted(years_b)})"
                )
                updated[target_i] = target_d.model_copy(update={
                    "action": DecisionAction.FLAG,
                    "annotation": annotation,
                })
                logger.info("[decision] Internal contradiction flagged for '%s'", shared)

        return updated

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
