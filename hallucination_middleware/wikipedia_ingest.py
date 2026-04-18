"""
Wikipedia ingestion module.

Fetches Wikipedia articles and stores them in the ChromaDB knowledge base.
Requires: pip install wikipedia-api
"""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def ingest_from_wikipedia(topic: str, language: str = "en") -> int:
    """
    Fetch a Wikipedia article and ingest it into the knowledge base.

    Parameters
    ----------
    topic : str
        Wikipedia page title (e.g., "Albert Einstein", "GDPR")
    language : str
        Wikipedia language code. Default: 'en' (English)

    Returns
    -------
    int
        Number of chunks added. 0 if page not found or error.
    """
    try:
        import wikipediaapi  # noqa: PLC0415
    except ImportError:
        logger.error(
            "wikipedia-api not installed. Run: pip install wikipedia-api"
        )
        return 0

    wiki = wikipediaapi.Wikipedia(
        user_agent="HallucinationMiddleware/2.0 (research-project)",
        language=language,
    )

    page = wiki.page(topic)
    if not page.exists():
        logger.warning("[Wikipedia] Page not found: '%s'", topic)
        return 0

    from .knowledge_base import KnowledgeBase  # noqa: PLC0415

    kb = KnowledgeBase()
    source = f"wikipedia:{topic}"
    chunks = kb.ingest_text(page.text, source=source)
    logger.info("[Wikipedia] Ingested '%s' → %d chunks", topic, chunks)
    return chunks


def ingest_multiple(topics: List[str], language: str = "en") -> dict:
    """
    Ingest multiple Wikipedia topics at once.

    Returns dict mapping topic → chunks_added.
    """
    results = {}
    for topic in topics:
        results[topic] = ingest_from_wikipedia(topic, language=language)
    return results


def search_wikipedia(query: str, n_results: int = 5, language: str = "en") -> List[str]:
    """
    Search Wikipedia for pages matching a query.
    Returns list of matching page titles.
    """
    try:
        import wikipediaapi  # noqa: PLC0415
    except ImportError:
        return []

    wiki = wikipediaapi.Wikipedia(
        user_agent="HallucinationMiddleware/2.0 (research-project)",
        language=language,
    )
    page = wiki.page(query)
    if page.exists():
        return [page.title]

    # Try common variations
    variations = [
        query.title(),
        query.lower(),
        query.replace(" ", "_"),
    ]
    found = []
    for v in variations:
        p = wiki.page(v)
        if p.exists() and p.title not in found:
            found.append(p.title)
        if len(found) >= n_results:
            break
    return found
