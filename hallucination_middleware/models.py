"""
Core data models for the hallucination detection middleware.

Flow: ExtractedClaim → VerifiedClaim → ClaimDecision → HallucinationAudit
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone


class ClaimType(str, Enum):
    ENTITY = "entity"
    STATISTIC = "statistic"
    DATE = "date"
    CITATION = "citation"
    LEGAL = "legal"
    MEDICAL = "medical"
    GEOGRAPHIC = "geographic"
    CAUSAL = "causal"


class ClaimStakes(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"
    PARTIALLY_SUPPORTED = "partially_supported"


class DecisionAction(str, Enum):
    PASS = "pass"
    ANNOTATE = "annotate"
    FLAG = "flag"
    BLOCK = "block"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class ExtractedClaim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str
    normalized: str
    claim_type: ClaimType
    stakes: ClaimStakes
    span_start: int
    span_end: int


# ---------------------------------------------------------------------------
# Retrieval metadata (new — tracks advanced retrieval pipeline)
# ---------------------------------------------------------------------------

class RetrievalMetadata(BaseModel):
    claim_id: str = ""
    query_variants: List[str] = []    # All queries used (original + expansions + HyDE)
    total_retrieved: int = 0          # Docs retrieved before re-ranking
    total_after_rerank: int = 0       # Docs kept after re-ranking
    cache_hit: bool = False           # Result served from cache
    ensemble_used: bool = False       # Ensemble verification was used


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class SupportingDocument(BaseModel):
    doc_id: str
    source: str
    excerpt: str
    relevance_score: float
    rerank_score: Optional[float] = None   # Cross-encoder score (if re-ranked)


class VerifiedClaim(BaseModel):
    claim: ExtractedClaim
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_docs: List[SupportingDocument] = []
    contradiction_reason: Optional[str] = None
    verification_reasoning: str = ""
    key_evidence: str = ""


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

class ClaimDecision(BaseModel):
    verified_claim: VerifiedClaim
    action: DecisionAction
    annotation: str = ""


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class HallucinationAudit(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    model: str = ""

    # Aggregate counts (populated by finalize())
    total_claims: int = 0
    verified_count: int = 0
    partially_supported_count: int = 0
    unverifiable_count: int = 0
    contradicted_count: int = 0
    pass_count: int = 0
    annotate_count: int = 0
    flagged_count: int = 0
    blocked_count: int = 0
    cache_hits: int = 0

    overall_confidence: float = 1.0
    response_blocked: bool = False
    block_reason: Optional[str] = None
    processing_time_ms: float = 0.0

    claims: List[ClaimDecision] = []
    retrieval_metadata: List[RetrievalMetadata] = []
    original_text: str = ""
    annotated_text: str = ""

    def finalize(self, original_text: str = "", processing_time_ms: float = 0.0) -> None:
        self.total_claims = len(self.claims)
        self.verified_count = sum(
            1 for c in self.claims if c.verified_claim.status == VerificationStatus.VERIFIED
        )
        self.partially_supported_count = sum(
            1 for c in self.claims
            if c.verified_claim.status == VerificationStatus.PARTIALLY_SUPPORTED
        )
        self.unverifiable_count = sum(
            1 for c in self.claims
            if c.verified_claim.status == VerificationStatus.UNVERIFIABLE
        )
        self.contradicted_count = sum(
            1 for c in self.claims
            if c.verified_claim.status == VerificationStatus.CONTRADICTED
        )
        self.pass_count = sum(1 for c in self.claims if c.action == DecisionAction.PASS)
        self.annotate_count = sum(1 for c in self.claims if c.action == DecisionAction.ANNOTATE)
        self.flagged_count = sum(1 for c in self.claims if c.action == DecisionAction.FLAG)
        self.blocked_count = sum(1 for c in self.claims if c.action == DecisionAction.BLOCK)
        self.cache_hits = sum(1 for m in self.retrieval_metadata if m.cache_hit)

        if self.claims:
            self.overall_confidence = round(
                sum(c.verified_claim.confidence for c in self.claims) / len(self.claims), 3
            )
        else:
            self.overall_confidence = 1.0

        self.response_blocked = self.blocked_count > 0
        if self.response_blocked:
            blocked = [c for c in self.claims if c.action == DecisionAction.BLOCK]
            previews = "; ".join(
                f'"{c.verified_claim.claim.text[:50]}..."' for c in blocked[:3]
            )
            self.block_reason = (
                f"Response contains {self.blocked_count} blocked claim(s): {previews}"
            )

        self.original_text = original_text
        self.processing_time_ms = round(processing_time_ms, 2)
