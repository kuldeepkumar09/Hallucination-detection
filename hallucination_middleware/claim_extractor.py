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

def _selection(sentences: List[Tuple[str, int, int]]) -> List[Tuple[str, int, int]]:
    """Stage 2: Selection - keep sentences that look verifiable, drop pure opinion."""
    factual_keywords = [
        'is', 'was', 'are', 'were', 'has', 'have', 'had',
        'contains', 'includes', 'equals', 'amounts to',
        'developed', 'invented', 'created', 'founded', 'discovered',
        'born', 'died', 'became', 'won', 'lost', 'published',
        'located', 'known', 'called', 'named', 'defined',
        'percent', '%', 'million', 'billion', 'thousand',
    ]
    opinion_markers = ['i think', 'in my opinion', 'i believe', 'i feel', 'i suggest']
    selected = []
    for sent, start, end in sentences:
        lower_sent = sent.lower()
        if len(sent.strip()) < 10:
            continue
        if any(word in lower_sent for word in opinion_markers):
            continue
        if any(kw in lower_sent for kw in factual_keywords):
            selected.append((sent, start, end))
    # Fallback: if nothing passed the filter, include everything ≥ 10 chars
    if not selected:
        selected = [(s, st, en) for s, st, en in sentences if len(s.strip()) >= 10]
    return selected

def _decomposition(sentences: List[Tuple[str, int, int]]) -> List[str]:
    """Stage 4: Decomposition - break into atomic claims."""
    atomic_claims = []
    for sent, _, _ in sentences:
        # Split on conjunctions like 'and', 'but', etc.
        parts = re.split(r'\s+(and|but|or|however|although)\s+', sent)
        for part in parts:
            if len(part.strip()) > 10:  # Filter short fragments
                atomic_claims.append(part.strip())
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
                                     "legal", "medical", "geographic", "causal"],
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
Extract verifiable factual claims from the text. Output ONLY a JSON object, nothing else.

Format (start with { end with }):
{"claims":[{"text":"exact claim","normalized":"self-contained form","claim_type":"entity","stakes":"medium","category":"GENERAL"}]}

claim_type: entity | statistic | date | geographic | causal | medical | legal | citation
stakes: critical | high | medium | low
category: MEDICAL | LEGAL | FINANCIAL | GENERAL

Rules:
- Only concrete checkable facts, not opinions or advice.
- normalized: MUST be ≤ 25 words. Concise, third-person restatement only — no extra context.
- normalized must be self-contained (replace pronouns with the actual subject).
- medical/legal/safety facts get stakes=critical.
- Use MEDICAL for drug/dose/diagnosis/treatment claims.
- Use LEGAL for law/regulation/court/fine/date-of-law claims.
- Use FINANCIAL for market/price/GDP/interest rate/economic claims.
- Use GENERAL for everything else (history, science, geography, tech).
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

        # NVIDIA NIM is OpenAI-compatible — use the same client with NIM base URL
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
        self._ollama_request_extra: dict = {}

    async def extract(self, text: str) -> List[ExtractedClaim]:
        """
        Extract factual claims from *text* using Claimify methodology.
        Returns an empty list on failure — never raises.
        """
        if not text.strip():
            return []

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
        # NVIDIA NIM hangs on json_object constrained generation for some models — skip it
        use_json_formats = (False,) if s.llm_provider == "nvidia_nim" else (True, False)
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
                break
            except Exception as exc:
                if not use_json_format:
                    logger.error("Claim extraction error: %s", exc)
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
