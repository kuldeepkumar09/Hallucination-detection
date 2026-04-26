"""Atomic Fact Extractor — extracts (Subject, Predicate, Object) triplets.

Uses NVIDIA NIM when available, falls back to Ollama.
Each triplet represents one indivisible fact: ("Einstein", "was born in", "Ulm").
"""
import json
import logging
import re
from typing import List

from openai import AsyncOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)

TRIPLET_SYSTEM = """\
Extract atomic fact triplets from the text. Each triplet = one indivisible fact.
Format: (Subject, Predicate, Object) — Subject must be explicit, no pronouns.

Output ONLY valid JSON:
{"triplets":[{"subject":"Einstein","predicate":"was born in","object":"Ulm, Germany","claim":"Einstein was born in Ulm, Germany"}]}

Rules:
- One fact per triplet only.
- Subject is always the full explicit name/entity (never "he", "she", "it").
- Keep predicate short (2-5 words).
- claim is a complete readable sentence combining subject+predicate+object.
- Extract only verifiable facts, not opinions."""


class NIMExtractor:
    """Extracts atomic (Subject, Predicate, Object) triplets."""

    def __init__(self):
        s = get_settings()
        if s.llm_provider == "nvidia_nim" and s.nvidia_nim_api_key:
            self._client = AsyncOpenAI(
                base_url=s.nvidia_nim_base_url,
                api_key=s.nvidia_nim_api_key,
                timeout=60.0,
            )
            self._model = "meta/llama-3.1-8b-instruct"
        else:
            self._client = AsyncOpenAI(
                base_url=s.ollama_base_url,
                api_key="ollama",
                timeout=60.0,
            )
            self._model = s.extractor_model

    async def extract_triplets(self, text: str) -> List[dict]:
        """Extract (S, P, O) triplets. Returns [] on failure."""
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": TRIPLET_SYSTEM},
                    {"role": "user", "content": f"Extract triplets:\n{text[:4000]}"},
                ],
                temperature=0.0,
            )
            content = resp.choices[0].message.content or ""
            content = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()
            start = content.find("{")
            if start > 0:
                content = content[start:]
            data = json.loads(content)
            return data.get("triplets", [])
        except Exception as exc:
            logger.debug("[NIMExtractor] triplet extraction failed: %s", exc)
            return []
