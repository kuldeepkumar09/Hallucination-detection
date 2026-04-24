"""
Hallucination Detection Middleware v3 — Public API
"""
from .audit_trail import AuditTrail
from .cache import ClaimCache
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .web_search import web_search_evidence, web_search_evidence_async
from .wikipedia_ingest import ingest_from_wikipedia, ingest_multiple
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
    "web_search_evidence",
    "web_search_evidence_async",
    "ingest_from_wikipedia",
    "ingest_multiple",
]
