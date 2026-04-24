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

        # NVIDIA NIM is OpenAI-compatible — same client, different base URL
        if s.llm_provider == "nvidia_nim":
            self._client = AsyncOpenAI(
                base_url=s.nvidia_nim_base_url,
                api_key=s.nvidia_nim_api_key,
                timeout=s.request_timeout,
            )
        else:
            self._client = AsyncOpenAI(
                base_url=s.ollama_base_url,
                api_key=s.ollama_api_key,
                timeout=s.request_timeout,
            )

    async def correct(
        self,
        original_text: str,
        decisions: List[ClaimDecision],
    ) -> Optional[str]:
        """
        Returns corrected text if any BLOCK/FLAG claims were found and
        self-correction is enabled. Returns None otherwise (caller keeps original).
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
                return await self._correct_anthropic(prompt)
            return await self._correct_ollama(prompt)
        except Exception as exc:
            logger.warning("Self-correction failed: %s", exc)
            return None

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
                    model=s.verifier_model,
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
                    model=s.verifier_model,
                    max_tokens=4096,
                    system=CORRECTION_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                corrected = response.content[0].text.strip() if response.content else ""
                if corrected:
                    logger.info("Self-correction (Anthropic) applied (%d chars)", len(corrected))
                    return corrected
            except Exception as exc:
                wait = 2 ** attempt
                if attempt < 2:
                    logger.warning("Correction (Anthropic) attempt %d failed, retrying in %ds: %s", attempt + 1, wait, exc)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Anthropic correction failed after 3 attempts: %s", exc)
        return None
