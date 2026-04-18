"""
Claim Extractor — uses a local Ollama LLM (free, no API key) to pull
structured factual claims from arbitrary LLM output text.

Falls back gracefully if the model is unavailable or returns malformed JSON.
"""
import json
import logging
import re
from typing import List

from openai import AsyncOpenAI

from .config import get_settings
from .models import ClaimStakes, ClaimType, ExtractedClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a precision fact-extraction engine. Extract every verifiable factual claim from the text.

Rules:
- Extract ONLY concrete, checkable facts (not opinions, advice, or hedged statements).
- Each claim must be independently verifiable against an authoritative source.
- Normalize claims to be fully self-contained (include the subject even when a pronoun was used).
- Mark medical, legal, and safety claims as 'critical' stakes.

Do NOT extract:
- Pure opinions ("this is excellent")
- General advice ("you should exercise")
- Hedged statements ("might be", "could possibly")

Respond with ONLY a JSON object in this exact format (no markdown, no explanation):
{
  "claims": [
    {
      "text": "exact claim text from source",
      "normalized": "self-contained clarified form of the claim",
      "claim_type": "entity|statistic|date|citation|legal|medical|geographic|causal",
      "stakes": "critical|high|medium|low",
      "span_start": 0,
      "span_end": 50
    }
  ]
}

claim_type values:
  entity = person/org/thing with a property
  statistic = number/percentage
  date = temporal fact
  citation = attributed quote/source
  legal = law/regulation
  medical = health/drug/clinical
  geographic = location fact
  causal = cause-effect claim

stakes values:
  critical = safety/legal/medical harm possible if wrong
  high = significant factual claim
  medium = general knowledge
  low = trivial detail
"""


def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from LLM output.
    Handles: clean JSON, markdown code blocks, JSON embedded in text.
    """
    if not text:
        return {}

    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {}


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------


class ClaimExtractor:
    """Async claim extractor backed by a local Ollama LLM (free, no API key)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        s = self.settings

        if s.llm_provider == "anthropic":
            try:
                import anthropic as _anthropic
                self._anthropic_client = _anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
            except ImportError:
                logger.warning("anthropic package not installed, falling back to ollama")
                self._anthropic_client = None
        else:
            self._anthropic_client = None

        self._client = AsyncOpenAI(
            base_url=s.ollama_base_url,
            api_key=s.ollama_api_key,
            timeout=s.request_timeout,  # configurable timeout; defaults to 8 min for slow model loads
        )

    async def extract(self, text: str) -> List[ExtractedClaim]:
        """
        Extract factual claims from *text*.
        Returns an empty list on failure — never raises.
        """
        if not text.strip():
            return []

        if self._anthropic_client is not None:
            return await self._extract_anthropic(text)
        return await self._extract_ollama(text)

    # ------------------------------------------------------------------
    # Ollama (free) path
    # ------------------------------------------------------------------

    async def _extract_ollama(self, text: str) -> List[ExtractedClaim]:
        s = self.settings
        user_msg = (
            "Extract all factual claims from the following text. "
            "Return ONLY valid JSON, no explanation:\n\n"
            f"{text}"
        )

        try:
            response = await self._client.chat.completions.create(
                model=s.extractor_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
        except Exception:
            # Some Ollama versions don't support response_format — retry without it
            try:
                response = await self._client.chat.completions.create(
                    model=s.extractor_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.1,
                )
                content = response.choices[0].message.content or ""
            except Exception as exc:
                logger.error("Claim extraction error: %s", exc)
                return []

        data = _extract_json(content)
        raw_claims = data.get("claims", [])
        if not raw_claims:
            logger.warning("Extractor returned no claims")
        return self._parse_claims(raw_claims, text)

    # ------------------------------------------------------------------
    # Anthropic (paid) path — kept as fallback
    # ------------------------------------------------------------------

    async def _extract_anthropic(self, text: str) -> List[ExtractedClaim]:
        from .claim_extractor_anthropic import CLAIM_EXTRACTION_TOOL  # noqa: PLC0415
        s = self.settings
        try:
            response = await self._anthropic_client.messages.create(
                model=s.extractor_model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Extract all factual claims from:\n\n<text>\n{text}\n</text>",
                }],
                tools=[CLAIM_EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_factual_claims"},
            )
        except Exception as exc:
            logger.error("Claim extraction API error: %s", exc)
            return []

        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_factual_claims":
                return self._parse_claims(block.input.get("claims", []), text)
        return []

    # ------------------------------------------------------------------
    # Shared parser
    # ------------------------------------------------------------------

    def _parse_claims(self, raw: list, text: str) -> List[ExtractedClaim]:
        claims: List[ExtractedClaim] = []
        max_claims = self.settings.max_claims_per_response
        text_len = len(text)
        text_lower = text.lower()

        for item in raw[:max_claims]:
            try:
                claim_text = str(item.get("text", "")).strip()
                if not claim_text:
                    continue

                # Compute span: use provided values or search in original text
                span_start = item.get("span_start")
                span_end = item.get("span_end")
                if span_start is None or span_end is None:
                    idx = text_lower.find(claim_text.lower())
                    if idx >= 0:
                        span_start = idx
                        span_end = idx + len(claim_text)
                    else:
                        span_start = 0
                        span_end = min(len(claim_text), text_len)

                span_start = max(0, int(span_start))
                span_end = min(text_len, int(span_end))
                span_end = max(span_end, span_start + 1)

                raw_type = str(item.get("claim_type", "entity")).split("|")[0].strip().lower()
                raw_stakes = str(item.get("stakes", "medium")).split("|")[0].strip().lower()
                valid_types = {e.value for e in ClaimType}
                valid_stakes = {e.value for e in ClaimStakes}
                if raw_type not in valid_types:
                    raw_type = "entity"
                if raw_stakes not in valid_stakes:
                    raw_stakes = "medium"

                claims.append(
                    ExtractedClaim(
                        text=claim_text,
                        normalized=str(item.get("normalized", claim_text)),
                        claim_type=ClaimType(raw_type),
                        stakes=ClaimStakes(raw_stakes),
                        span_start=span_start,
                        span_end=span_end,
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed claim %s: %s", item, exc)

        return claims
