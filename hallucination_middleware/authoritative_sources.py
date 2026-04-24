"""
Authoritative Data Sources Integration — Domain-specific knowledge sources for enhanced verification.

Provides integrations with:
- Medical: PubMed, FDA, WHO, CDC APIs
- Legal: CourtListener, Legal Information Institute
- Financial: SEC EDGAR, World Bank, IMF APIs
- General: Wikipedia, Britannica, official government sources
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """Types of authoritative sources."""
    MEDICAL = "medical"
    LEGAL = "legal"
    FINANCIAL = "financial"
    GENERAL = "general"
    SCIENTIFIC = "scientific"
    NEWS = "news"


@dataclass
class SourceDocument:
    """Document from an authoritative source."""
    source_id: str
    source_type: SourceType
    source_name: str
    title: str
    content: str
    url: str
    published_date: Optional[str]
    authority_score: float  # 0.0-1.0 based on source credibility
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthoritativeSource:
    """Base class for authoritative data sources."""
    
    name: str = "base"
    source_type: SourceType = SourceType.GENERAL
    base_url: str = ""
    authority_score: float = 0.8
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search the source for relevant documents."""
        raise NotImplementedError
    
    async def get_document(self, doc_id: str) -> Optional[SourceDocument]:
        """Retrieve a specific document by ID."""
        raise NotImplementedError


# ── Medical Sources ───────────────────────────────────────────────────────

class PubMedSource(AuthoritativeSource):
    """PubMed biomedical literature search."""
    
    name = "PubMed"
    source_type = SourceType.MEDICAL
    base_url = "https://pubmed.ncbi.nlm.nih.gov"
    authority_score = 0.98
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search PubMed for medical literature."""
        try:
            import aiohttp
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            }
            
            documents = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ids = data.get("esearchresult", {}).get("idlist", [])
                        
                        # Fetch details for each ID
                        if ids:
                            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                            fetch_params = {
                                "db": "pubmed",
                                "id": ",".join(ids),
                                "retmode": "json",
                            }
                            async with session.get(fetch_url, params=fetch_params, timeout=30) as fetch_resp:
                                if fetch_resp.status == 200:
                                    fetch_data = await fetch_resp.json()
                                    articles = fetch_data.get("pubmedresult", [])
                                    
                                    for article in articles[:max_results]:
                                        doc = self._parse_article(article)
                                        if doc:
                                            documents.append(doc)
            
            return documents
        except Exception as exc:
            logger.debug(f"PubMed search failed: {exc}")
            return []
    
    def _parse_article(self, article: dict) -> Optional[SourceDocument]:
        """Parse PubMed article into SourceDocument."""
        try:
            medline_citation = article.get("medlinecitation", {})
            article_data = medline_citation.get("article", {})
            
            title = article_data.get("articletitle", "")
            abstract = article_data.get("abstract", "")
            
            if isinstance(abstract, dict):
                abstract_text = ""
                for section in abstract.get("abstractsection", []):
                    for para in section.get("paragraph", []):
                        abstract_text += para.get("text", "") + "\n"
                abstract = abstract_text
            elif isinstance(abstract, list):
                abstract = "\n".join(abstract)
            
            pmid = medline_citation.get("pmid", "")
            
            return SourceDocument(
                source_id=f"pubmed_{pmid}",
                source_type=SourceType.MEDICAL,
                source_name=self.name,
                title=title,
                content=abstract or title,
                url=f"{self.base_url}/{pmid}",
                published_date=article_data.get("articledate", ""),
                authority_score=self.authority_score,
                metadata={"pmid": pmid},
            )
        except Exception:
            return None


class FDASource(AuthoritativeSource):
    """FDA drug and device information."""
    
    name = "FDA"
    source_type = SourceType.MEDICAL
    base_url = "https://www.fda.gov"
    authority_score = 0.99
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search FDA open data APIs."""
        try:
            import aiohttp
            # FDA OpenFDA API for drug labels
            url = "https://api.fda.gov/drug/label.json"
            params = {
                "search": f"(openfda.brand_name:{query} OR openfda.generic_name:{query} OR indications_and_usage:{query})",
                "limit": max_results,
            }
            
            documents = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for result in data.get("results", [])[:max_results]:
                            doc = self._parse_drug_label(result)
                            if doc:
                                documents.append(doc)
            
            return documents
        except Exception as exc:
            logger.debug(f"FDA search failed: {exc}")
            return []
    
    def _parse_drug_label(self, label: dict) -> Optional[SourceDocument]:
        """Parse FDA drug label into SourceDocument."""
        try:
            openfda = label.get("openfda", {})
            brand_name = openfda.get("brand_name", [""])[0]
            generic_name = openfda.get("generic_name", [""])[0]
            
            indications = label.get("indications_and_usage", [""])[0] if label.get("indications_and_usage") else ""
            warnings = label.get("warnings", [""])[0] if label.get("warnings") else ""
            
            content = f"Indications: {indications}\n\nWarnings: {warnings}"
            
            return SourceDocument(
                source_id=f"fda_{brand_name}",
                source_type=SourceType.MEDICAL,
                source_name=self.name,
                title=f"{brand_name} ({generic_name}) - FDA Label",
                content=content[:2000],
                url=f"{self.base_url}/drugs",
                published_date=None,
                authority_score=self.authority_score,
                metadata={"brand_name": brand_name, "generic_name": generic_name},
            )
        except Exception:
            return None


# ── Legal Sources ─────────────────────────────────────────────────────────

class CourtListenerSource(AuthoritativeSource):
    """CourtListener legal case search."""
    
    name = "CourtListener"
    source_type = SourceType.LEGAL
    base_url = "https://www.courtlistener.com"
    authority_score = 0.95
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search CourtListener for legal cases."""
        try:
            import aiohttp
            url = "https://www.courtlistener.com/api/rest/v4/opinions/"
            params = {
                "q": query,
                "format": "json",
                "order_by": "score",
                "size": max_results,
            }
            
            documents = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers={"User-Agent": "HallucinationDetector/1.0"}, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for case in data.get("results", [])[:max_results]:
                            doc = self._parse_case(case)
                            if doc:
                                documents.append(doc)
            
            return documents
        except Exception as exc:
            logger.debug(f"CourtListener search failed: {exc}")
            return []
    
    def _parse_case(self, case: dict) -> Optional[SourceDocument]:
        """Parse legal case into SourceDocument."""
        try:
            return SourceDocument(
                source_id=f"court_{case.get('id', '')}",
                source_type=SourceType.LEGAL,
                source_name=self.name,
                title=case.get("caseName", ""),
                content=case.get("text", "")[:2000] if case.get("text") else case.get("snippet", ""),
                url=f"{self.base_url}{case.get('absolute_url', '')}",
                published_date=case.get("dateFiled", ""),
                authority_score=self.authority_score,
                metadata={
                    "court": case.get("docket", {}).get("court", ""),
                    "citation": case.get("citation", ""),
                },
            )
        except Exception:
            return None


# ── Financial Sources ─────────────────────────────────────────────────────

class SECEdgarSource(AuthoritativeSource):
    """SEC EDGAR financial filings search."""
    
    name = "SEC EDGAR"
    source_type = SourceType.FINANCIAL
    base_url = "https://www.sec.gov/edgar"
    authority_score = 0.99
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search SEC EDGAR for financial filings."""
        try:
            import aiohttp
            # SEC company search
            url = "https://efts.sec.gov/LATEST/companyIndex"
            params = {
                "searchText": query,
                "start": 0,
                "count": max_results,
            }
            
            documents = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for filing in data.get("hits", [])[:max_results]:
                            doc = self._parse_filing(filing)
                            if doc:
                                documents.append(doc)
            
            return documents
        except Exception as exc:
            logger.debug(f"SEC EDGAR search failed: {exc}")
            return []
    
    def _parse_filing(self, filing: dict) -> Optional[SourceDocument]:
        """Parse SEC filing into SourceDocument."""
        try:
            return SourceDocument(
                source_id=f"sec_{filing.get('id', '')}",
                source_type=SourceType.FINANCIAL,
                source_name=self.name,
                title=f"{filing.get('display', '')} - {filing.get('formType', '')}",
                content=f"Company: {filing.get('display', '')}\nForm: {filing.get('formType', '')}\nFiled: {filing.get('filedAt', '')}",
                url=f"https://www.sec.gov{filing.get('linkXsl', '')}",
                published_date=filing.get("filedAt", ""),
                authority_score=self.authority_score,
                metadata={
                    "form_type": filing.get("formType", ""),
                    "company": filing.get("display", ""),
                },
            )
        except Exception:
            return None


class WorldBankSource(AuthoritativeSource):
    """World Bank economic data."""
    
    name = "World Bank"
    source_type = SourceType.FINANCIAL
    base_url = "https://data.worldbank.org"
    authority_score = 0.95
    
    async def search(self, query: str, max_results: int = 5) -> List[SourceDocument]:
        """Search World Bank for economic indicators."""
        try:
            import aiohttp
            # World Bank API for indicators
            url = "http://api.worldbank.org/v2/indicator"
            params = {
                "format": "json",
                "search": query,
                "per_page": max_results,
            }
            
            documents = []
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) > 1:
                            for indicator in data[1][:max_results]:
                                doc = self._parse_indicator(indicator)
                                if doc:
                                    documents.append(doc)
            
            return documents
        except Exception as exc:
            logger.debug(f"World Bank search failed: {exc}")
            return []
    
    def _parse_indicator(self, indicator: dict) -> Optional[SourceDocument]:
        """Parse World Bank indicator into SourceDocument."""
        try:
            return SourceDocument(
                source_id=f"wb_{indicator.get('id', '')}",
                source_type=SourceType.FINANCIAL,
                source_name=self.name,
                title=indicator.get("name", ""),
                content=indicator.get("sourceNote", ""),
                url=f"{self.base_url}/indicator/{indicator.get('id', '')}",
                published_date=None,
                authority_score=self.authority_score,
                metadata={"indicator_id": indicator.get("id", "")},
            )
        except Exception:
            return None


# ── Source Manager ────────────────────────────────────────────────────────

class SourceManager:
    """
    Manages all authoritative data sources.
    
    Features:
    - Source registration and discovery
    - Parallel multi-source search
    - Result deduplication and ranking
    - Caching for performance
    """
    
    def __init__(self):
        self._sources: Dict[str, AuthoritativeSource] = {}
        self._cache: Dict[str, List[SourceDocument]] = {}
        self._cache_ttl = timedelta(hours=24)
        self._register_default_sources()
    
    def _register_default_sources(self) -> None:
        """Register default authoritative sources."""
        self.register(PubMedSource())
        self.register(FDASource())
        self.register(CourtListenerSource())
        self.register(SECEdgarSource())
        self.register(WorldBankSource())
    
    def register(self, source: AuthoritativeSource) -> None:
        """Register an authoritative source."""
        self._sources[source.name] = source
        logger.info(f"Registered authoritative source: {source.name} ({source.source_type.value})")
    
    def unregister(self, name: str) -> None:
        """Unregister a source."""
        if name in self._sources:
            del self._sources[name]
    
    async def search(
        self, 
        query: str, 
        source_types: List[SourceType] = None,
        max_results: int = 10
    ) -> List[SourceDocument]:
        """
        Search across multiple authoritative sources.
        
        Args:
            query: Search query
            source_types: Filter by source types (None = all)
            max_results: Maximum total results to return
        
        Returns:
            List of SourceDocument ranked by authority score
        """
        # Check cache first
        cache_key = f"{query}:{source_types}:{max_results}"
        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_result
        
        # Filter sources by type
        sources_to_search = [
            source for source in self._sources.values()
            if source_types is None or source.source_type in source_types
        ]
        
        if not sources_to_search:
            return []
        
        # Search all sources in parallel
        tasks = [
            source.search(query, max_results)
            for source in sources_to_search
        ]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten and deduplicate
        all_docs: List[SourceDocument] = []
        seen_ids: set = set()
        
        for results in results_lists:
            if isinstance(results, list):
                for doc in results:
                    if doc.source_id not in seen_ids:
                        seen_ids.add(doc.source_id)
                        all_docs.append(doc)
        
        # Rank by authority score
        all_docs.sort(key=lambda d: d.authority_score, reverse=True)
        
        # Cache results
        self._cache[cache_key] = (all_docs[:max_results], datetime.now())
        
        return all_docs[:max_results]
    
    def get_sources_by_type(self, source_type: SourceType) -> List[AuthoritativeSource]:
        """Get all sources of a specific type."""
        return [s for s in self._sources.values() if s.source_type == source_type]
    
    def get_all_sources(self) -> List[AuthoritativeSource]:
        """Get all registered sources."""
        return list(self._sources.values())
    
    def clear_cache(self) -> None:
        """Clear the source cache."""
        self._cache.clear()


# ── Global Source Manager ─────────────────────────────────────────────────

_source_manager: Optional[SourceManager] = None


def get_source_manager() -> SourceManager:
    """Get or create global source manager."""
    global _source_manager
    if _source_manager is None:
        _source_manager = SourceManager()
    return _source_manager


async def search_authoritative_sources(
    query: str,
    source_types: List[SourceType] = None,
    max_results: int = 10
) -> List[SourceDocument]:
    """Search across authoritative sources."""
    return await get_source_manager().search(query, source_types, max_results)


def register_source(source: AuthoritativeSource) -> None:
    """Register a new authoritative source."""
    get_source_manager().register(source)