"""
Claim Extractor — uses a local Ollama LLM (free, no API key) to pull
structured factual claims from arbitrary LLM output text.

Implements Claimify methodology: Sentence Splitting, Selection, Disambiguation, Decomposition.

Falls back gracefully if the model is unavailable or returns malformed JSON.
"""
import json
import logging
import re
from typing import List, Tuple

from openai import AsyncOpenAI

from .config import get_settings
from .models import ClaimStakes, ClaimType, ExtractedClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Claimify Stages
# ---------------------------------------------------------------------------

def _sentence_split(text: str) -> List[Tuple[str, int, int]]:
    """Stage 1: Sentence Splitting with context preservation."""
    try:
        import spacy
        spacy_model = get_settings().spacy_language_model
        nlp = spacy.load(spacy_model, disable=["ner", "parser", "tagger"])
        nlp.enable_pipe("senter")
        doc = nlp(text[:100_000])
        sentences = []
        for sent in doc.sents:
            start = sent.start_char
            end = sent.end_char
            sentences.append((sent.text.strip(), start, end))
        return sentences
    except ImportError:
        # Fallback to simple splitting
        sentences = re.split(r'(?<=[.!?])\s+', text)
        result = []
        offset = 0
        for sent in sentences:
            start = text.find(sent, offset)
            end = start + len(sent)
            result.append((sent.strip(), start, end))
            offset = end
        return result

_OPINION_MARKERS = {
    'i think', 'i believe', 'i feel', 'i suggest', 'in my opinion', 'in my view',
    'it seems', 'it appears', 'arguably', 'perhaps', 'probably', 'possibly',
    'i would say', 'i would argue', 'one could argue', 'some might say',
    'it could be', 'it might be', 'many believe', 'some believe',
    'the best', 'the worst', 'the greatest', 'most beautiful', 'most important',
    'should', 'ought to', 'must be', 'may be better', 'is better than',
}

_PREDICTION_MARKERS = {
    'will be', 'will have', 'will become', 'will increase', 'will decrease',
    'is expected to', 'are expected to', 'is projected to', 'is forecast to',
    'is predicted to', 'is likely to', 'is set to', 'is poised to',
    'by 2025', 'by 2026', 'by 2030', 'in the future', 'in coming years',
    'next year', 'next decade', 'upcoming', 'anticipated',
}

_CREATIVE_MARKERS = {
    'once upon a time', 'in the story', 'in the novel', 'the character',
    'fictionally', 'hypothetically', 'imagine if', 'suppose that',
    'in this scenario', 'as a metaphor', 'for the sake of argument',
    'in a world where', 'if we assume',
}

def _classify_sentence(sent: str) -> str:
    """Return 'factual' | 'opinion' | 'prediction' | 'creative'."""
    lower = sent.lower()
    if any(m in lower for m in _CREATIVE_MARKERS):
        return 'creative'
    if any(m in lower for m in _PREDICTION_MARKERS):
        return 'prediction'
    if any(m in lower for m in _OPINION_MARKERS):
        return 'opinion'
    return 'factual'


def _selection(sentences: List[Tuple[str, int, int]]) -> List[Tuple[str, int, int, str]]:
    """Stage 2: Selection — tag each sentence with its type for the LLM hint."""
    selected: List[Tuple[str, int, int, str]] = []
    for sent, start, end in sentences:
        if len(sent.strip()) < 10:
            continue
        kind = _classify_sentence(sent)
        selected.append((sent, start, end, kind))
    if not selected:
        selected = [(s, st, en, "factual") for s, st, en in sentences if len(s.strip()) >= 10]
    return selected

def _decomposition(sentences: List[Tuple[str, int, int, str]]) -> List[str]:
    """Stage 4: Decomposition - break into atomic claims, prefixed with sentence type."""
    atomic_claims = []
    for sent, _, _, kind in sentences:
        # Split on conjunctions like 'and', 'but', etc.
        parts = re.split(r'\s+(and|but|or|however|although)\s+', sent)
        for part in parts:
            if len(part.strip()) > 10:
                # Prefix with type so the LLM uses it as a classification hint
                atomic_claims.append(f"[{kind.upper()}] {part.strip()}")
    return atomic_claims

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CLAIM_EXTRACTION_TOOL = {
    "name": "extract_factual_claims",
    "description": "Extract all verifiable factual claims from the text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "normalized": {"type": "string"},
                        "claim_type": {
                            "type": "string",
                            "enum": ["entity", "statistic", "date", "citation",
                                     "legal", "medical", "geographic", "causal",
                                     "opinion", "prediction", "creative"],
                        },
                        "stakes": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low"],
                        },
                        "category": {
                            "type": "string",
                            "enum": ["MEDICAL", "LEGAL", "FINANCIAL", "GENERAL"],
                        },
                    },
                    "required": ["text", "normalized", "claim_type", "stakes", "category"],
                },
            }
        },
        "required": ["claims"],
    },
}

SYSTEM_PROMPT = """\
Extract ALL claims from the text — factual, opinion, prediction, and creative. Output ONLY JSON.

Format (start with { end with }):
{"claims":[{"text":"exact claim","normalized":"self-contained form","claim_type":"entity","stakes":"medium","category":"GENERAL"}]}

claim_type options:
  FACTUAL types (will be verified against sources):
    entity | statistic | date | geographic | causal | medical | legal | citation
  NON-FACTUAL types (auto-passed, not verified):
    opinion    — subjective judgement, preference, recommendation ("the best", "I think", "arguably")
    prediction — future-tense or forecast claim ("will", "expected to", "by 2030")
    creative   — fictional, hypothetical, metaphorical content ("imagine if", "in the story")

stakes: critical | high | medium | low (use low for opinion/prediction/creative)
category: MEDICAL | LEGAL | FINANCIAL | GENERAL

Rules:
- Include ALL claims including opinions and predictions — tag them correctly so they are not falsely flagged.
- normalized: MUST be ≤ 25 words. Concise, third-person restatement. Replace pronouns with subject.
- medical/legal/safety factual claims get stakes=critical.
- opinions and predictions always get stakes=low.
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

        # Route primary client by provider
        if s.llm_provider == "nvidia_nim":
            self._client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
        elif s.llm_provider == "together":
            self._client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
            self._anthropic_client = None
        else:
            self._client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key, timeout=s.request_timeout)
        self._ollama_request_extra: dict = {}

        # Fallback: NVIDIA NIM when primary=together, Together AI when primary=anthropic/nvidia_nim
        self._fallback_client = None
        if s.llm_provider == "together" and s.nvidia_nim_api_key:
            self._fallback_client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
            logger.info("NVIDIA NIM fallback ready for claim extraction")
        elif s.fallback_enabled and s.together_api_key and s.together_api_key not in ("", "your-together-api-key-here"):
            self._fallback_client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
            logger.info("Together AI fallback ready for claim extraction")

    async def extract(self, text: str) -> List[ExtractedClaim]:
        """
        Extract factual claims from *text* using Claimify methodology.
        Returns an empty list on failure — never raises.
        """
        if not text.strip():
            return []

        # Coreference resolution: replace "He/She/It" with explicit referents
        s = self.settings
        if s.coref_enabled:
            try:
                from .core.coref_handler import resolve_coreferences
                text = resolve_coreferences(text)
            except Exception:
                pass

        # Claimify Pipeline
        sentences = _sentence_split(text)
        selected = _selection(sentences)
        atomic_claims = _decomposition(selected)

        if not atomic_claims:
            return []

        # Now extract structured claims from atomic claims using LLM
        if self._anthropic_client is not None:
            return await self._extract_anthropic(text)
        return await self._extract_ollama_from_atoms(atomic_claims, text)

    # ------------------------------------------------------------------
    # Ollama (free) path with Claimify
    # ------------------------------------------------------------------

    async def _extract_ollama_from_atoms(self, atomic_claims: List[str], full_text: str) -> List[ExtractedClaim]:
        s = self.settings
        # Send original text; include Claimify candidate sentences as a hint.
        # 12 000 chars ≈ 3 000 tokens — leaves room for prompt overhead and response
        # within a 4096-token context while covering ~3× more text than the old 4 000 limit.
        _MAX_TEXT = 12_000
        text_for_llm = full_text if len(full_text) <= _MAX_TEXT else full_text[:_MAX_TEXT]
        hint = "\n".join(f"- {c}" for c in atomic_claims[:s.max_claims_per_response])
        user_msg = (
            f"Text:\n{text_for_llm}\n\n"
            f"Candidate factual sentences (pre-filtered):\n{hint}\n\n"
            "Extract all verifiable claims. Return ONLY the JSON object."
        )

        content = ""
        # NVIDIA NIM hangs on json_object constrained generation — skip it; Together AI supports it
        use_json_formats = (False,) if s.llm_provider == "nvidia_nim" else (True, False)
        last_exc = None
        for use_json_format in use_json_formats:
            try:
                kwargs: dict = {
                    "model": s.extractor_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.0,
                    **self._ollama_request_extra,
                }
                if use_json_format:
                    kwargs["response_format"] = {"type": "json_object"}
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if not use_json_format:
                    break

        if last_exc is not None:
            exc_str = str(last_exc).lower()
            is_fallback_trigger = any(kw in exc_str for kw in (
                "429", "rate limit", "rate_limit", "overloaded", "529", "503",
                "credit balance", "billing", "insufficient", "402", "quota", "401",
            ))
            if is_fallback_trigger and self._fallback_client is not None:
                logger.warning("Primary extractor failed (%s) — using fallback", last_exc)
                return await self._extract_via_fallback(atomic_claims, full_text)
            logger.error("Claim extraction error: %s", last_exc)
            return []

        data = _extract_json(content)
        raw_claims = data.get("claims", [])
        if not raw_claims:
            logger.warning("Extractor returned no claims. Raw output: %s", content[:200])
        return self._parse_claims(raw_claims, full_text)

    # ------------------------------------------------------------------
    # Anthropic (paid) path — kept as fallback
    # ------------------------------------------------------------------

    async def _extract_anthropic(self, text: str) -> List[ExtractedClaim]:
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
            for block in response.content:
                if block.type == "tool_use" and block.name == "extract_factual_claims":
                    return self._parse_claims(block.input.get("claims", []), text)
            return []
        except Exception as exc:
            exc_str = str(exc).lower()
            is_fallback_trigger = any(kw in exc_str for kw in (
                "429", "rate limit", "rate_limit", "overloaded", "529", "503",
                "credit balance", "billing", "insufficient", "402", "quota",
            ))
            if is_fallback_trigger and self._fallback_client is not None:
                logger.warning("Primary extraction failed (%s) — using fallback", exc)
                sentences = _sentence_split(text)
                selected = _selection(sentences)
                atomic_claims = _decomposition(selected)
                return await self._extract_via_fallback(atomic_claims, text)
            logger.error("Claim extraction API error: %s", exc)
            return []

    async def _extract_via_fallback(self, atomic_claims: List[str], text: str) -> List[ExtractedClaim]:
        """Fallback extraction using the secondary client (NIM or Together AI)."""
        s = self.settings
        hint = "\n".join(f"- {c}" for c in atomic_claims[:s.max_claims_per_response])
        _MAX_TEXT = 12_000
        text_for_llm = text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT]
        user_msg = (
            f"Text:\n{text_for_llm}\n\n"
            f"Candidate factual sentences (pre-filtered):\n{hint}\n\n"
            "Extract all verifiable claims. Return ONLY the JSON object."
        )
        # Pick fallback model name based on which provider is fallback
        if s.llm_provider == "together":
            fallback_model = "meta/llama-3.1-8b-instruct"  # NIM model name
        else:
            fallback_model = s.together_extractor_model
        try:
            response = await self._fallback_client.chat.completions.create(
                model=fallback_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
            )
            content = response.choices[0].message.content or ""
            data = _extract_json(content)
            raw_claims = data.get("claims", [])
            if not raw_claims:
                logger.warning("Fallback extractor returned no claims. Raw: %s", content[:200])
            logger.info("Fallback extraction succeeded (%d claims, model=%s)", len(raw_claims), fallback_model)
            return self._parse_claims(raw_claims, text)
        except Exception as exc:
            logger.error("Fallback extraction also failed: %s", exc)
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
                # phi3:mini sometimes returns plain strings instead of dicts
                if isinstance(item, str):
                    item = {"text": item, "normalized": item}

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

                raw_category = str(item.get("category", "GENERAL")).strip().upper()
                valid_categories = {"MEDICAL", "LEGAL", "FINANCIAL", "GENERAL"}
                if raw_category not in valid_categories:
                    raw_category = "GENERAL"

                # Prevent overly verbose normalized forms from degrading KB retrieval
                normalized = str(item.get("normalized", claim_text)).strip()
                if len(normalized.split()) > 35:
                    normalized = " ".join(normalized.split()[:35])

                claims.append(
                    ExtractedClaim(
                        text=claim_text,
                        normalized=normalized,
                        claim_type=ClaimType(raw_type),
                        stakes=ClaimStakes(raw_stakes),
                        span_start=span_start,
                        span_end=span_end,
                        category=raw_category,
                    )
                )
            except (KeyError, ValueError, AttributeError, TypeError) as exc:
                logger.warning("Skipping malformed claim %s: %s", item, exc)

        return claims
