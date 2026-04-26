"""Ollama wrapper for Gemma-2B (4-bit quantized) — generates text to be verified."""
import logging
from openai import AsyncOpenAI
from ..config import get_settings
from .hardware_guard import is_vram_safe

logger = logging.getLogger(__name__)


class GemmaClient:
    """Async client for Ollama-hosted Gemma-2B (gemma2:2b)."""

    def __init__(self, model: str = "gemma2:2b"):
        s = get_settings()
        self._model = model
        self._client = AsyncOpenAI(
            base_url=s.ollama_base_url,
            api_key="ollama",
            timeout=120.0,
        )

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        if not is_vram_safe():
            logger.warning("[GemmaClient] VRAM near limit — skipping generation to prevent OOM")
            return ""
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error("[GemmaClient] Generation failed: %s", exc)
            return ""
