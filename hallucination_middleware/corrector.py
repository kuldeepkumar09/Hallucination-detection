"""
Self-Correction Loop — intercepts BLOCK/FLAG claims and asks the LLM to
silently fix its own hallucinations before returning to the user.

Flow:
  1. Collect all BLOCK + FLAG decisions after the normal pipeline.
  2. Build a correction prompt: original text + each error with correct evidence.
  3. Call the LLM once to produce a revised version.
  4. Return the corrected text (or original if correction fails/is disabled).
"""
import asyncio
import logging
import re
from typing import List, Optional

from openai import AsyncOpenAI

from .config import get_settings
from .models import ClaimDecision, DecisionAction

logger = logging.getLogger(__name__)

CORRECTION_SYSTEM = """\
You are a precise text editor. You will be given an original text that contains
factual errors, and a list of corrections with authoritative evidence.

Your task:
- Rewrite ONLY the parts of the text that contain the listed errors.
- Apply each correction using the provided evidence.
- Keep the rest of the text identical — do not paraphrase, summarize, or add content.
- Do not add disclaimers, notes, or explanations.
- Return the corrected text only, with no preamble.
"""


def _find_corrected_sentence(corrected_text: str, original_claim: str) -> str:
    """
    Find the sentence in corrected_text that most closely matches original_claim.
    Uses word-overlap scoring so the NLI re-verification targets the right sentence.
    """
    sentences = re.split(r'(?<=[.!?])\s+', corrected_text)
    if not sentences:
        return corrected_text[:300]
    orig_words = set(original_claim.lower().split())
    best = max(sentences, key=lambda s: len(orig_words & set(s.lower().split())))
    return best[:300]


class SelfCorrector:
    """
    Rewrites an LLM response to fix hallucinations detected by the pipeline.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._settings = s
        self._enabled = s.self_correction_enabled

        if s.llm_provider == "anthropic":
            try:
                import anthropic as _anthropic
                self._anthropic_client = _anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
            except ImportError:
                logger.warning("anthropic package not installed, falling back to ollama")
                self._anthropic_client = None
        else:
            self._anthropic_client = None

        # Route primary client by provider
        if s.llm_provider == "nvidia_nim":
            self._client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
        elif s.llm_provider == "together":
            self._client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
            self._anthropic_client = None
        else:
            self._client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key, timeout=s.request_timeout)

        # Fallback: NVIDIA NIM when primary=together, Together AI otherwise
        self._fallback_client = None
        if s.llm_provider == "together" and s.nvidia_nim_api_key:
            self._fallback_client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
        elif s.fallback_enabled and s.together_api_key and s.together_api_key not in ("", "your-together-api-key-here"):
            self._fallback_client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)

    async def correct(
        self,
        original_text: str,
        decisions: List[ClaimDecision],
    ) -> Optional[str]:
        """
        Returns corrected text if any BLOCK/FLAG claims were found and
        self-correction is enabled, AND the NLI re-verification confirms the
        correction improved factual accuracy.  Returns None otherwise.
        """
        if not self._enabled:
            return None

        issues = [
            d for d in decisions
            if d.action in (DecisionAction.BLOCK, DecisionAction.FLAG)
        ]
        if not issues:
            return None

        correction_items = self._build_corrections(issues)
        if not correction_items:
            return None

        prompt = self._build_prompt(original_text, correction_items)

        try:
            if self._anthropic_client is not None:
                corrected = await self._correct_anthropic(prompt)
            else:
                corrected = await self._correct_ollama(prompt)
        except Exception as exc:
            logger.warning("Self-correction failed: %s", exc)
            return None

        if not corrected:
            return None

        # ── NLI re-verification: confirm correction actually improved things ──
        # Run the NLI scorer on (corrected_claim, original_evidence) pairs.
        # If fewer than half the flagged claims improve under NLI, revert.
        corrected = await self._nli_verify_correction(corrected, issues)
        return corrected

    async def _nli_verify_correction(
        self,
        corrected_text: str,
        original_issues: List[ClaimDecision],
    ) -> Optional[str]:
        """
        Lightweight NLI check: for each originally flagged claim, see if the
        corrected text now contains text that entails (rather than contradicts)
        the key evidence.  If the correction degraded more than it improved,
        return None to keep the original text.
        """
        try:
            from .nli_scorer import get_nli_scorer  # noqa: PLC0415
            nli = get_nli_scorer()
            if nli is None:
                return corrected_text  # NLI not available — trust the correction

            improved = 0
            checked = 0
            for decision in original_issues:
                vc = decision.verified_claim
                evidence = vc.key_evidence or (
                    vc.supporting_docs[0].excerpt if vc.supporting_docs else ""
                )
                if not evidence:
                    continue
                # Score original claim vs evidence
                orig_score = nli.score(vc.claim.text, evidence)
                orig_entail = orig_score.get("entailment", 0.0) if orig_score else 0.0
                # Score the corrected version of THIS specific claim (not the full text)
                corr_sentence = _find_corrected_sentence(corrected_text, vc.claim.text)
                corr_score = nli.score(corr_sentence, evidence)
                corr_entail = corr_score.get("entailment", 0.0) if corr_score else 0.0
                if corr_entail > orig_entail:
                    improved += 1
                checked += 1

            if checked == 0:
                return corrected_text  # no scoreable pairs — accept correction

            improvement_ratio = improved / checked
            logger.info(
                "[corrector] NLI re-verification: %d/%d claims improved (ratio=%.2f)",
                improved, checked, improvement_ratio,
            )
            if improvement_ratio >= 0.5:  # majority of claims must improve
                return corrected_text
            logger.info("[corrector] Correction rejected by NLI re-verification (ratio=%.2f)", improvement_ratio)
            return None
        except Exception as exc:
            logger.debug("[corrector] NLI re-verification skipped: %s", exc)
            return corrected_text  # on any error, trust the correction

    # ------------------------------------------------------------------

    def _build_corrections(self, issues: List[ClaimDecision]) -> List[str]:
        items = []
        for d in issues:
            vc = d.verified_claim
            claim_text = vc.claim.text
            evidence = vc.key_evidence or (
                vc.supporting_docs[0].excerpt if vc.supporting_docs else ""
            )
            reason = vc.contradiction_reason or vc.verification_reasoning or d.annotation
            if evidence:
                items.append(
                    f'ERROR: "{claim_text}"\n'
                    f'REASON: {reason[:200]}\n'
                    f'CORRECT EVIDENCE: {evidence[:400]}'
                )
            else:
                items.append(
                    f'ERROR: "{claim_text}"\n'
                    f'REASON: {reason[:200]}'
                )
        return items

    def _build_prompt(self, original_text: str, corrections: List[str]) -> str:
        corrections_block = "\n\n".join(
            f"[Correction {i + 1}]\n{c}" for i, c in enumerate(corrections)
        )
        return (
            f"ORIGINAL TEXT:\n{original_text}\n\n"
            f"CORRECTIONS TO APPLY:\n{corrections_block}\n\n"
            "Rewrite the original text applying all corrections. "
            "Return only the corrected text."
        )

    async def _correct_ollama(self, prompt: str) -> Optional[str]:
        s = self._settings
        for attempt in range(3):
            try:
                response = await self._client.chat.completions.create(
                    model=s.extractor_model,
                    messages=[
                        {"role": "system", "content": CORRECTION_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                corrected = (response.choices[0].message.content or "").strip()
                if corrected:
                    logger.info("Self-correction applied (%d chars)", len(corrected))
                    return corrected
            except Exception as exc:
                wait = 2 ** attempt
                if attempt < 2:
                    logger.warning("Correction attempt %d failed, retrying in %ds: %s", attempt + 1, wait, exc)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Self-correction failed after 3 attempts: %s", exc)
        return None

    async def _correct_anthropic(self, prompt: str) -> Optional[str]:
        s = self._settings
        for attempt in range(3):
            try:
                response = await self._anthropic_client.messages.create(
                    model=s.extractor_model,
                    max_tokens=4096,
                    system=CORRECTION_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                corrected = response.content[0].text.strip() if response.content else ""
                if corrected:
                    logger.info("Self-correction (Anthropic) applied (%d chars)", len(corrected))
                    return corrected
            except Exception as exc:
                exc_str = str(exc).lower()
                is_rate_limit = any(kw in exc_str for kw in ("429", "rate limit", "rate_limit", "overloaded", "529", "503", "credit balance", "billing", "insufficient", "402", "quota"))
                if is_rate_limit and self._fallback_client is not None:
                    logger.warning("Anthropic rate-limited in corrector — using Together AI fallback")
                    try:
                        fb_resp = await self._fallback_client.chat.completions.create(
                            model=s.together_extractor_model,
                            messages=[
                                {"role": "system", "content": CORRECTION_SYSTEM},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.1,
                        )
                        corrected = (fb_resp.choices[0].message.content or "").strip()
                        if corrected:
                            logger.info("Self-correction (Together AI fallback) applied (%d chars)", len(corrected))
                            return corrected
                    except Exception as fb_exc:
                        logger.warning("Together AI corrector fallback failed: %s", fb_exc)
                wait = 2 ** attempt
                if attempt < 2:
                    logger.warning("Correction (Anthropic) attempt %d failed, retrying in %ds: %s", attempt + 1, wait, exc)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Anthropic correction failed after 3 attempts: %s", exc)
        return None
