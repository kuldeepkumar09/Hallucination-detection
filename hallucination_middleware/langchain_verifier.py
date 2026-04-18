"""
LangChain Verification Chain.

Provides a LangChain-based orchestration layer that:
  1. Retrieves evidence from ChromaDB (RAG)
  2. Optionally augments with live web search
  3. Runs structured verification prompt through local Ollama LLM
  4. Returns VerifiedClaim-compatible result dict

This is an OPTIONAL enhancement — the core pipeline uses the direct
Verifier class. Use this module when you want LangChain orchestration
for scalability or want to swap LLMs easily.

Requires: pip install langchain langchain-community langchain-openai
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

VERIFICATION_PROMPT = """\
You are a rigorous fact-checker. Verify the following claim using only the provided evidence.

CLAIM:
{claim}

EVIDENCE FROM AUTHORITATIVE SOURCES:
{evidence}

Based ONLY on the evidence above, determine:
- status: "verified", "contradicted", "partially_supported", or "unverifiable"
- confidence: float 0.0 to 1.0
- reasoning: one sentence explaining your decision
- key_evidence: the most relevant quote from the evidence (empty string if none)

Return ONLY valid JSON, no explanation:
{{"status": "verified", "confidence": 0.85, "reasoning": "...", "key_evidence": "..."}}
"""

ENTITY_EXTRACTION_PROMPT = """\
Extract all verifiable factual entities from the following text.
Return ONLY a JSON array of search queries — one query per fact to verify.
Focus on: names, dates, statistics, locations, laws, medical claims.

TEXT:
{text}

Return JSON array:
["query 1", "query 2", "query 3"]
"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _extract_json_list(text: str) -> list:
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            pass
    return []


# ---------------------------------------------------------------------------
# LangChain Chain Builder
# ---------------------------------------------------------------------------

class LangChainVerificationChain:
    """
    LangChain-based verification chain for hallucination detection.

    Supports easy LLM swapping: change the model name in .env and
    the entire pipeline updates automatically.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = None
        self._chain = None
        self._available = False
        self._init_chain()

    def _init_chain(self) -> None:
        try:
            from langchain_openai import ChatOpenAI          # noqa: PLC0415
            from langchain.prompts import ChatPromptTemplate  # noqa: PLC0415

            s = self._settings
            self._llm = ChatOpenAI(
                base_url=s.ollama_base_url,
                api_key=s.ollama_api_key,
                model=s.verifier_model,
                temperature=0.1,
            )

            prompt = ChatPromptTemplate.from_template(VERIFICATION_PROMPT)
            self._chain = prompt | self._llm
            self._available = True
            logger.info("[LangChain] Verification chain initialized (%s)", s.verifier_model)
        except ImportError:
            logger.warning(
                "[LangChain] langchain-openai not installed — LangChain chain disabled. "
                "Run: pip install langchain langchain-openai"
            )
        except Exception as exc:
            logger.warning("[LangChain] Chain init failed: %s", exc)

    def is_available(self) -> bool:
        return self._available and self._chain is not None

    def verify_claim(self, claim: str, evidence: str) -> Dict[str, Any]:
        """
        Verify a single claim against provided evidence using LangChain.

        Returns dict with keys: status, confidence, reasoning, key_evidence
        """
        if not self.is_available():
            return {
                "status": "unverifiable",
                "confidence": 0.3,
                "reasoning": "LangChain not available",
                "key_evidence": "",
            }

        try:
            result = self._chain.invoke({"claim": claim, "evidence": evidence})
            content = result.content if hasattr(result, "content") else str(result)
            data = _extract_json(content)

            return {
                "status": data.get("status", "unverifiable"),
                "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.3)))),
                "reasoning": data.get("reasoning", ""),
                "key_evidence": data.get("key_evidence", ""),
            }
        except Exception as exc:
            logger.error("[LangChain] Verification error: %s", exc)
            return {
                "status": "unverifiable",
                "confidence": 0.3,
                "reasoning": f"Chain error: {exc}",
                "key_evidence": "",
            }

    def extract_search_queries(self, text: str) -> List[str]:
        """
        Use LangChain to extract targeted search queries from LLM output.
        These queries are used to fetch evidence from KB and web search.
        """
        if not self.is_available():
            return [text[:200]]

        try:
            from langchain.prompts import ChatPromptTemplate  # noqa: PLC0415
            prompt = ChatPromptTemplate.from_template(ENTITY_EXTRACTION_PROMPT)
            chain = prompt | self._llm
            result = chain.invoke({"text": text})
            content = result.content if hasattr(result, "content") else str(result)
            queries = _extract_json_list(content)
            return [q for q in queries if isinstance(q, str) and q.strip()][:10]
        except Exception as exc:
            logger.warning("[LangChain] Query extraction failed: %s", exc)
            return [text[:200]]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_chain_instance: Optional[LangChainVerificationChain] = None


def get_langchain_chain() -> LangChainVerificationChain:
    """Get or create the singleton LangChain verification chain."""
    global _chain_instance
    if _chain_instance is None:
        _chain_instance = LangChainVerificationChain()
    return _chain_instance
