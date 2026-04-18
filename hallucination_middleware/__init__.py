"""
Hallucination Detection Middleware v2 — Public API

New in v2:
    ClaimCache            — claim-level verification cache (in-memory + Redis)
    CrossEncoderReranker  — cross-encoder document re-ranker
    RetrievalMetadata     — per-claim retrieval audit (query variants, re-rank counts)
    wikipedia_ingest      — Wikipedia article ingestion helpers
    web_search            — Tavily + DuckDuckGo live web verification
    langchain_verifier    — LangChain orchestration chain (optional)
"""
from .audit_trail import AuditTrail
from .cache import ClaimCache
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .web_search import web_search_evidence, web_search_evidence_async
from .wikipedia_ingest import ingest_from_wikipedia, ingest_multiple
from .langchain_verifier import get_langchain_chain
from .models import (
    ClaimDecision,
    ClaimStakes,
    ClaimType,
    DecisionAction,
    ExtractedClaim,
    HallucinationAudit,
    RetrievalMetadata,
    SupportingDocument,
    VerificationStatus,
    VerifiedClaim,
)
from .pipeline import HallucinationDetectionPipeline
from .reranker import CrossEncoderReranker

__all__ = [
    "HallucinationDetectionPipeline",
    "KnowledgeBase",
    "AuditTrail",
    "ClaimCache",
    "CrossEncoderReranker",
    "HallucinationAudit",
    "RetrievalMetadata",
    "ClaimDecision",
    "ClaimType",
    "ClaimStakes",
    "DecisionAction",
    "ExtractedClaim",
    "SupportingDocument",
    "VerificationStatus",
    "VerifiedClaim",
    "get_settings",
    # New v2.1
    "web_search_evidence",
    "web_search_evidence_async",
    "ingest_from_wikipedia",
    "ingest_multiple",
    "get_langchain_chain",
]
