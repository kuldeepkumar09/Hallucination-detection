"""
Source Credibility Scorer — fixes the "web search returns wrong sources" limitation.

Two mechanisms:
1. Domain trust tiers: Wikipedia, .gov, .edu, major journals/news = high trust.
   Random blogs, forums, unknown sites = low trust.
   Credibility score adjusts effective relevance before the verifier sees the docs.

2. Contradiction cross-validation: a CONTRADICTED verdict is only accepted if
   at least 2 independent (different root domains) sources agree it is wrong.
   A single low-trust source cannot block an LLM response.
"""
import logging
import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain trust tiers  [0.0 – 1.0]
# ---------------------------------------------------------------------------

# Tier 1 (0.95): primary authoritative sources
_TIER1 = {
    "wikipedia.org", "britannica.com",
    "nature.com", "science.org", "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov", "nih.gov", "cdc.gov", "who.int",
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "theguardian.com", "washingtonpost.com",
    "arxiv.org", "scholar.google.com",
    "ieee.org", "acm.org",
    "loc.gov", "congress.gov", "supremecourt.gov",
}

# Tier 2 (0.80): respected but not primary
_TIER2 = {
    "smithsonianmag.com", "scientificamerican.com", "newscientist.com",
    "theatlantic.com", "economist.com", "ft.com", "wsj.com",
    "time.com", "nationalgeographic.com",
    "merriam-webster.com", "oxforddictionaries.com",
    "mayoclinic.org", "webmd.com", "healthline.com",
    "investopedia.com", "bloomberg.com",
    "history.com", "historyextra.com",
    "imdb.com",  # factual data (dates, directors, etc.)
}

# Tier 3 (0.65): government + edu TLDs (any subdomain)
_TIER3_TLDS = {".gov", ".edu", ".ac.uk", ".ac.in", ".edu.au"}

# Tier 4 (0.50): known aggregators/encyclopedias that may be user-edited
_TIER4 = {"simple.wikipedia.org", "wikidata.org", "wikimedia.org", "dbpedia.org"}

# Default for unknown domains: 0.40
_DEFAULT_SCORE = 0.40

# Social media / forums — heavily penalised
_LOW_TRUST = {
    "reddit.com", "quora.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "tiktok.com", "pinterest.com", "tumblr.com",
    "stackoverflow.com",  # great for code, poor for factual verification
    "medium.com",  # user blogs, variable quality
}
_LOW_TRUST_SCORE = 0.20


def score_url(url: str) -> float:
    """Return a domain credibility score in [0.0, 1.0] for a web result URL."""
    if not url:
        return _DEFAULT_SCORE
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        hostname = parsed.hostname or ""
        hostname = hostname.lower().lstrip("www.")
    except Exception:
        return _DEFAULT_SCORE

    if not hostname:
        return _DEFAULT_SCORE

    if hostname in _LOW_TRUST:
        return _LOW_TRUST_SCORE

    if hostname in _TIER1:
        return 0.95

    if hostname in _TIER4:
        return 0.50

    if hostname in _TIER2:
        return 0.80

    # Tier 3: TLD-based check
    for tld in _TIER3_TLDS:
        if hostname.endswith(tld):
            return 0.65

    # Any .gov or .edu deeper subdomains
    parts = hostname.split(".")
    if len(parts) >= 2 and f".{parts[-1]}" in {".gov", ".edu"}:
        return 0.65

    return _DEFAULT_SCORE


def score_documents(docs: List[Dict]) -> List[Dict]:
    """
    Add a 'credibility_score' key to each document dict and adjust
    'relevance_score' by blending it with domain credibility.

    Blended score = 0.6 * relevance + 0.4 * credibility
    This means a high-relevance but low-trust source cannot dominate.
    """
    for doc in docs:
        url = doc.get("source", "")
        cred = score_url(url)
        doc["credibility_score"] = round(cred, 3)
        raw_rel = doc.get("relevance_score", 0.5)
        doc["relevance_score"] = round(0.6 * raw_rel + 0.4 * cred, 4)
    return docs


def _root_domain(url: str) -> str:
    """Extract root domain (e.g. 'bbc.com') from a URL."""
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        hostname = (parsed.hostname or "").lower().lstrip("www.")
        parts = hostname.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else hostname
    except Exception:
        return url


def validate_contradiction(docs: List[Dict], threshold: int = 2) -> Tuple[bool, float]:
    """
    Cross-validation gate for CONTRADICTED verdicts.

    A contradiction is only trusted when at least `threshold` documents from
    DIFFERENT root domains support it (i.e., it is not a single-source claim).

    Returns:
        (accepted, avg_credibility)
        accepted=True  → contradiction is cross-validated, keep CONTRADICTED
        accepted=False → only one source; downgrade to PARTIALLY_SUPPORTED
    """
    if not docs:
        return False, 0.0

    # Only count docs with meaningful credibility
    credible_docs = [d for d in docs if d.get("credibility_score", 0.0) >= 0.35]
    if not credible_docs:
        return False, 0.0

    domains = {_root_domain(d.get("source", "")) for d in credible_docs}
    avg_cred = sum(d.get("credibility_score", 0.4) for d in credible_docs) / len(credible_docs)

    accepted = len(domains) >= threshold
    if not accepted:
        logger.info(
            "[credibility] Contradiction rejected: only %d domain(s), need %d. Downgrading to partially_supported.",
            len(domains), threshold,
        )
    return accepted, round(avg_cred, 3)
