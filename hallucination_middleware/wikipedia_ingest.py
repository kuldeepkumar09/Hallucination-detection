"""
Wikipedia ingestion module — powered by wikipedia-api (pip install wikipedia-api).

Features:
  - search_wikipedia()    : Real Wikipedia OpenSearch (returns titles + snippets)
  - get_page_info()       : Page metadata — title, summary, sections, categories
  - ingest_from_wikipedia(): Full article OR summary-only ingestion
  - ingest_sections()     : Ingest specific named sections only
  - ingest_multiple()     : Batch ingest multiple topics
"""
import logging
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "HallucinationMiddleware/2.0 (https://github.com/local/hallucination-middleware; contact@example.com)"


# ---------------------------------------------------------------------------
# Wikipedia API client (shared, lazy-init)
# ---------------------------------------------------------------------------

def _get_wiki(language: str = "en"):
    """Return a wikipediaapi.Wikipedia instance for the given language."""
    try:
        import wikipediaapi  # noqa: PLC0415
    except ImportError:
        raise ImportError("Run: pip install wikipedia-api") from None
    return wikipediaapi.Wikipedia(user_agent=_USER_AGENT, language=language)


# ---------------------------------------------------------------------------
# Search — uses Wikipedia's OpenSearch API (real full-text search)
# ---------------------------------------------------------------------------

def search_wikipedia(
    query: str,
    n_results: int = 8,
    language: str = "en",
) -> List[Dict]:
    """
    Search Wikipedia and return a list of matching articles.

    Returns
    -------
    List of dicts: [{title, description, url}]
    """
    if not query.strip():
        return []

    url = f"https://{language}.wikipedia.org/w/api.php"
    # Use action=query&list=search (more permissive than opensearch)
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": n_results,
        "srnamespace": 0,
        "format": "json",
        "srprop": "snippet|titlesnippet",
    }
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("query", {}).get("search", [])
        results = []
        for hit in hits:
            title = hit.get("title", "")
            # Strip HTML tags from snippet
            import re as _re
            snippet = _re.sub(r"<[^>]+>", "", hit.get("snippet", ""))
            wiki_url = f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append({
                "title": title,
                "description": snippet,
                "url": wiki_url,
            })
        return results
    except Exception as exc:
        logger.warning("[Wikipedia search] Failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Page info — lightweight metadata without full ingestion
# ---------------------------------------------------------------------------

def get_page_info(topic: str, language: str = "en") -> Optional[Dict]:
    """
    Return metadata about a Wikipedia page without ingesting it.

    Returns dict with: title, summary (first 500 chars), url,
    section_count, categories (up to 10), exists.
    Returns None if page not found.
    """
    try:
        wiki = _get_wiki(language)
        page = wiki.page(topic)
        if not page.exists():
            return None

        sections = _collect_sections(page)
        categories = list(page.categories.keys())[:10]

        return {
            "title": page.title,
            "summary": page.summary[:600].rstrip() + ("…" if len(page.summary) > 600 else ""),
            "url": page.fullurl,
            "section_count": len(sections),
            "sections": [s["title"] for s in sections],
            "categories": categories,
            "text_length": len(page.text),
            "exists": True,
        }
    except Exception as exc:
        logger.warning("[Wikipedia info] Error for '%s': %s", topic, exc)
        return None


# ---------------------------------------------------------------------------
# Ingestion — full article, summary-only, or specific sections
# ---------------------------------------------------------------------------

def ingest_from_wikipedia(
    topic: str,
    language: str = "en",
    kb=None,
    mode: str = "full",       # "full" | "summary"
) -> int:
    """
    Fetch a Wikipedia article and ingest it into the knowledge base.

    Parameters
    ----------
    topic   : Wikipedia page title
    language: Wikipedia language code (default "en")
    kb      : KnowledgeBase instance (creates one if None)
    mode    : "full" → entire article text; "summary" → intro paragraph only

    Returns
    -------
    int: number of chunks added (0 on failure)
    """
    try:
        wiki = _get_wiki(language)
    except ImportError as exc:
        logger.error(str(exc))
        return 0

    page = wiki.page(topic)
    if not page.exists():
        logger.warning("[Wikipedia] Page not found: '%s'", topic)
        return 0

    if kb is None:
        from .knowledge_base import KnowledgeBase  # noqa: PLC0415
        kb = KnowledgeBase()

    source = f"wikipedia:{page.title}"

    if mode == "summary":
        text = page.summary
        if not text.strip():
            logger.warning("[Wikipedia] Empty summary for '%s'", topic)
            return 0
        chunks = kb.ingest_text(text, source=source)
        logger.info("[Wikipedia] Ingested summary of '%s' → %d chunks", page.title, chunks)
        return chunks

    # Full article
    text = page.text
    if not text.strip():
        logger.warning("[Wikipedia] Empty article for '%s'", topic)
        return 0
    chunks = kb.ingest_text(text, source=source)
    logger.info("[Wikipedia] Ingested full article '%s' → %d chunks (%d chars)", page.title, chunks, len(text))
    return chunks


def ingest_sections(
    topic: str,
    section_names: List[str],
    language: str = "en",
    kb=None,
) -> int:
    """
    Ingest only specific named sections of a Wikipedia article.

    Parameters
    ----------
    topic         : Wikipedia page title
    section_names : List of section titles to ingest (case-insensitive match)
    language      : Wikipedia language code

    Returns
    -------
    int: total chunks added across all matched sections
    """
    try:
        wiki = _get_wiki(language)
    except ImportError as exc:
        logger.error(str(exc))
        return 0

    page = wiki.page(topic)
    if not page.exists():
        logger.warning("[Wikipedia] Page not found: '%s'", topic)
        return 0

    if kb is None:
        from .knowledge_base import KnowledgeBase  # noqa: PLC0415
        kb = KnowledgeBase()

    lower_names = {n.lower() for n in section_names}
    all_sections = _collect_sections(page)
    total = 0
    for sec in all_sections:
        if sec["title"].lower() in lower_names and sec["text"].strip():
            source = f"wikipedia:{page.title}#{sec['title']}"
            chunks = kb.ingest_text(sec["text"], source=source)
            logger.info("[Wikipedia] Ingested section '%s › %s' → %d chunks", page.title, sec["title"], chunks)
            total += chunks

    if total == 0:
        logger.warning("[Wikipedia] No matching sections found in '%s'. Available: %s",
                       topic, [s["title"] for s in all_sections])
    return total


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def ingest_multiple(
    topics: List[str],
    language: str = "en",
    mode: str = "full",
    kb=None,
) -> Dict[str, int]:
    """
    Ingest multiple Wikipedia topics. Returns {topic: chunks_added}.
    """
    if kb is None:
        from .knowledge_base import KnowledgeBase  # noqa: PLC0415
        kb = KnowledgeBase()

    results = {}
    for topic in topics:
        results[topic] = ingest_from_wikipedia(topic, language=language, mode=mode, kb=kb)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_sections(page, parent_title: str = "") -> List[Dict]:
    """Recursively collect all sections with their text content."""
    sections = []

    def _walk(section_list, depth=0):
        for sec in section_list:
            if sec.text.strip():
                sections.append({
                    "title": sec.title,
                    "text": sec.text,
                    "depth": depth,
                })
            _walk(sec.sections, depth + 1)

    _walk(page.sections)
    return sections
