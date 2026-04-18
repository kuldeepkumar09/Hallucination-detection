"""
Web Search Verifier — Tavily (primary) + DuckDuckGo (free fallback).

Usage in pipeline:
    from .web_search import web_search_evidence
    evidence = await web_search_evidence(claim_text)

Priority:
  1. Tavily  — if TAVILY_API_KEY is set  (AI-optimized, clean results)
  2. DuckDuckGo — no API key required    (free fallback, always available)
"""
import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_TAVILY_WARNED = False
_DDG_WARNED = False


# ---------------------------------------------------------------------------
# Tavily search
# ---------------------------------------------------------------------------

def _search_tavily(query: str, max_results: int = 3) -> Optional[str]:
    """
    Search using Tavily API (AI-optimized results).
    Returns formatted evidence string or None on failure.
    """
    global _TAVILY_WARNED

    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from tavily import TavilyClient  # noqa: PLC0415
    except ImportError:
        if not _TAVILY_WARNED:
            logger.warning("tavily-python not installed. Run: pip install tavily-python")
            _TAVILY_WARNED = True
        return None

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_raw_content=False,
        )
        parts = []
        for r in response.get("results", []):
            parts.append(
                f"[Tavily] Source: {r.get('url', '')}\n"
                f"Title: {r.get('title', '')}\n"
                f"Content: {r.get('content', '')}"
            )
        text = "\n\n".join(parts)
        logger.debug("[Tavily] Got %d results for: %s", len(parts), query[:60])
        return text or None
    except Exception as exc:
        logger.warning("[Tavily] Search failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# DuckDuckGo search
# ---------------------------------------------------------------------------

def _search_duckduckgo(query: str, max_results: int = 3) -> Optional[str]:
    """
    Search using DuckDuckGo (no API key required).
    Returns formatted evidence string or None on failure.
    """
    global _DDG_WARNED

    try:
        try:
            from ddgs import DDGS  # noqa: PLC0415  (new package name)
        except ImportError:
            from duckduckgo_search import DDGS  # noqa: PLC0415  (legacy fallback)
    except ImportError:
        if not _DDG_WARNED:
            logger.warning("ddgs not installed. Run: pip install ddgs")
            _DDG_WARNED = True
        return None

    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)

        parts = []
        for r in results:
            parts.append(
                f"[DuckDuckGo] Source: {r.get('href', '')}\n"
                f"Title: {r.get('title', '')}\n"
                f"Snippet: {r.get('body', '')}"
            )
        text = "\n\n".join(parts)
        logger.debug("[DuckDuckGo] Got %d results for: %s", len(parts), query[:60])
        return text or None
    except Exception as exc:
        logger.warning("[DuckDuckGo] Search failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def web_search_evidence(query: str, max_results: int = 3) -> str:
    """
    Synchronous web search: tries Tavily first, falls back to DuckDuckGo.
    Returns formatted evidence text (empty string if both fail).
    """
    # Try Tavily first (better quality)
    result = _search_tavily(query, max_results=max_results)
    if result:
        return result

    # Fallback to DuckDuckGo (always free, no key)
    result = _search_duckduckgo(query, max_results=max_results)
    if result:
        return result

    logger.debug("[WebSearch] No results found for: %s", query[:60])
    return ""


async def web_search_evidence_async(query: str, max_results: int = 3) -> str:
    """Async wrapper for web_search_evidence."""
    return await asyncio.to_thread(web_search_evidence, query, max_results)


def web_search_batch(queries: List[str], max_results: int = 3) -> List[str]:
    """Search multiple queries, return list of evidence strings."""
    return [web_search_evidence(q, max_results) for q in queries]


async def web_search_batch_async(queries: List[str], max_results: int = 3) -> List[str]:
    """Async batch search — runs all queries concurrently."""
    tasks = [web_search_evidence_async(q, max_results) for q in queries]
    return list(await asyncio.gather(*tasks))
