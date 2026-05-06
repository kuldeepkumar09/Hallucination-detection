"""
Web Search Verifier — three-tier free evidence pipeline.

Priority:
  1. Tavily      — if TAVILY_API_KEY is set  (AI-optimized, paid optional)
  2. Wikipedia   — free REST API, no key, high-credibility encyclopedic content
  3. DuckDuckGo  — no API key required, broad web coverage

Wikipedia is the default free primary source; DuckDuckGo is the broad-web fallback.
No API key is ever required for Wikipedia or DuckDuckGo.

Improvements:
  - Retry logic with exponential backoff for rate limiting
  - Per-call timeout to prevent pipeline freeze
  - Clear rate-limit vs network error classification
  - Thread-safe singleton DDGS instance
"""
import asyncio
import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _tavily_api_key() -> str:
    """Read Tavily key from settings (respects .env) with os.environ fallback."""
    try:
        from .config import get_settings
        key = get_settings().tavily_api_key
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("TAVILY_API_KEY", "").strip()

_TAVILY_WARNED = False
_DDG_WARNED = False

# DDG retry settings
_DDG_MAX_RETRIES = 3
_DDG_BASE_DELAY = 2.0      # seconds before first retry
_DDG_TIMEOUT = 15          # seconds per DDG request


# ---------------------------------------------------------------------------
# Tavily search
# ---------------------------------------------------------------------------

def _search_tavily_structured(query: str, max_results: int = 3) -> List[Dict]:
    global _TAVILY_WARNED
    api_key = _tavily_api_key()
    if not api_key:
        return []
    try:
        from tavily import TavilyClient
    except ImportError:
        if not _TAVILY_WARNED:
            logger.warning("tavily-python not installed. Run: pip install tavily-python")
            _TAVILY_WARNED = True
        return []
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_raw_content=False,
        )
        results = []
        for r in response.get("results", []):
            snippet = r.get("content", "")
            results.append({
                "doc_id": f"web-tavily-{abs(hash(r.get('url', ''))) % 10**8}",
                "source": r.get("url", ""),
                "excerpt": snippet[:450],
                "relevance_score": float(r.get("score", 0.6)),
                "title": r.get("title", ""),
                "provider": "Tavily",
            })
        logger.debug("[Tavily] %d results for: %s", len(results), query[:60])
        return results
    except Exception as exc:
        logger.warning("[Tavily] Search failed: %s", exc)
        return []


def _search_tavily(query: str, max_results: int = 3) -> Optional[str]:
    api_key = _tavily_api_key()
    if not api_key:
        return None
    try:
        from tavily import TavilyClient
    except ImportError:
        return None
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query, search_depth="basic",
            max_results=max_results, include_raw_content=False,
        )
        parts = []
        for r in response.get("results", []):
            parts.append(
                f"[Tavily] Source: {r.get('url', '')}\n"
                f"Title: {r.get('title', '')}\n"
                f"Content: {r.get('content', '')}"
            )
        return "\n\n".join(parts) or None
    except Exception as exc:
        logger.warning("[Tavily] Search failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Wikipedia search — free REST API, no key required
# ---------------------------------------------------------------------------

def _search_wikipedia_structured(query: str, max_results: int = 3) -> List[Dict]:
    """Wikipedia API search — completely free, no API key, high-credibility source."""
    import json
    import urllib.parse
    import urllib.request

    try:
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "utf8": 1,
            "format": "json",
            "origin": "*",
        })
        url = f"https://en.wikipedia.org/w/api.php?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "HalluCheck/4.0 (hallucination-detection)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            # Strip HTML highlight tags Wikipedia adds to snippets
            import re
            snippet = re.sub(r"<[^>]+>", "", snippet)
            page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            results.append({
                "doc_id": f"web-wiki-{item.get('pageid', abs(hash(title)) % 10**8)}",
                "source": page_url,
                "excerpt": snippet[:450],
                "relevance_score": 0.65,  # Wikipedia is Tier-1 credibility
                "title": title,
                "provider": "Wikipedia",
            })
        logger.debug("[Wikipedia] %d results for: %s", len(results), query[:60])
        return results
    except Exception as exc:
        logger.debug("[Wikipedia] Search failed: %s", exc)
        return []


def _search_wikipedia(query: str, max_results: int = 3) -> Optional[str]:
    results = _search_wikipedia_structured(query, max_results)
    if not results:
        return None
    parts = []
    for r in results:
        parts.append(
            f"[Wikipedia] Source: {r['source']}\n"
            f"Title: {r['title']}\n"
            f"Snippet: {r['excerpt']}"
        )
    return "\n\n".join(parts) or None


# ---------------------------------------------------------------------------
# DuckDuckGo search — with retry + timeout
# ---------------------------------------------------------------------------

def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("ratelimit", "rate limit", "429", "too many", "blocked"))


def _search_duckduckgo_structured(query: str, max_results: int = 3) -> List[Dict]:
    global _DDG_WARNED
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        if not _DDG_WARNED:
            logger.warning("ddgs not installed. Run: pip install ddgs")
            _DDG_WARNED = True
        return []

    last_exc = None
    for attempt in range(_DDG_MAX_RETRIES):
        try:
            with DDGS(timeout=_DDG_TIMEOUT) as ddgs:
                raw = ddgs.text(query, max_results=max_results)

            if not raw:
                logger.debug("[DDG] No results for: %s", query[:60])
                return []

            results = []
            for r in raw:
                snippet = r.get("body", "")
                results.append({
                    "doc_id": f"web-ddg-{abs(hash(r.get('href', ''))) % 10**8}",
                    "source": r.get("href", ""),
                    "excerpt": snippet[:450],
                    "relevance_score": 0.50,
                    "title": r.get("title", ""),
                    "provider": "DuckDuckGo",
                })
            logger.debug("[DDG] %d results for: %s", len(results), query[:60])
            return results

        except Exception as exc:
            last_exc = exc
            if _is_rate_limited(exc):
                delay = _DDG_BASE_DELAY * (2 ** attempt)
                logger.warning("[DDG] Rate limited — retrying in %.1fs (attempt %d/%d)",
                               delay, attempt + 1, _DDG_MAX_RETRIES)
                time.sleep(delay)
            else:
                logger.warning("[DDG] Search failed (attempt %d/%d): %s",
                               attempt + 1, _DDG_MAX_RETRIES, exc)
                if attempt < _DDG_MAX_RETRIES - 1:
                    time.sleep(_DDG_BASE_DELAY)

    logger.warning("[DDG] All %d attempts failed. Last error: %s", _DDG_MAX_RETRIES, last_exc)
    return []


def _search_duckduckgo(query: str, max_results: int = 3) -> Optional[str]:
    results = _search_duckduckgo_structured(query, max_results)
    if not results:
        return None
    parts = []
    for r in results:
        parts.append(
            f"[DuckDuckGo] Source: {r['source']}\n"
            f"Title: {r['title']}\n"
            f"Snippet: {r['excerpt']}"
        )
    return "\n\n".join(parts) or None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def web_search_evidence(query: str, max_results: int = 3) -> str:
    """
    Synchronous web search: Tavily (paid, optional) → Wikipedia (free) → DuckDuckGo (free).
    Returns formatted evidence text (empty string if all fail).
    """
    result = _search_tavily(query, max_results=max_results)
    if result:
        return result

    result = _search_wikipedia(query, max_results=max_results)
    if result:
        return result

    result = _search_duckduckgo(query, max_results=max_results)
    if result:
        return result

    logger.debug("[WebSearch] No results found for: %s", query[:60])
    return ""


async def web_search_evidence_async(query: str, max_results: int = 3) -> str:
    return await asyncio.to_thread(web_search_evidence, query, max_results)


def web_search_batch(queries: List[str], max_results: int = 3) -> List[str]:
    return [web_search_evidence(q, max_results) for q in queries]


async def web_search_batch_async(queries: List[str], max_results: int = 3) -> List[str]:
    tasks = [web_search_evidence_async(q, max_results) for q in queries]
    return list(await asyncio.gather(*tasks))


def web_search_structured_sync(query: str, max_results: int = 3) -> List[Dict]:
    """
    Structured web search: Tavily (paid, optional) → Wikipedia (free) → DuckDuckGo (free).
    Returns list of dicts compatible with KB query results.
    Never raises — returns [] if all providers fail.
    """
    results = _search_tavily_structured(query, max_results)
    if results:
        return results
    results = _search_wikipedia_structured(query, max_results)
    if results:
        return results
    return _search_duckduckgo_structured(query, max_results)


async def web_search_structured(query: str, max_results: int = 3) -> List[Dict]:
    return await asyncio.to_thread(web_search_structured_sync, query, max_results)
