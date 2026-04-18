"""
Advanced Verifier — cross-checks extracted claims against the knowledge base.

Uses a local Ollama LLM (free, no API key required) for verification.
Supports: multi-query expansion, cross-encoder re-ranking, claim cache, ensemble.
"""
import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from .cache import ClaimCache
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .models import (
    ClaimStakes,
    ExtractedClaim,
    RetrievalMetadata,
    SupportingDocument,
    VerificationStatus,
    VerifiedClaim,
)
from .reranker import CrossEncoderReranker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM = """\
You are a rigorous fact-checker. Given claims and reference source documents, verify each claim.

Verification rules:
- VERIFIED: Claim is clearly and directly supported by the sources.
- CONTRADICTED: Claim directly conflicts with source information.
- PARTIALLY_SUPPORTED: Sources provide some support but not definitive confirmation.
- UNVERIFIABLE: Sources do not address the claim at all.

Confidence: 0.9+=very strong, 0.7=good, 0.5=moderate, 0.3=weak, 0.1=almost none.
Only mark VERIFIED with clear, direct evidence.
If no relevant sources listed for a claim, mark UNVERIFIABLE with confidence 0.3.

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "results": [
    {
      "claim_index": 0,
      "status": "verified|contradicted|partially_supported|unverifiable",
      "confidence": 0.85,
      "reasoning": "brief explanation",
      "key_evidence": "relevant quote from sources",
      "contradiction_reason": "why it contradicts (if applicable)"
    }
  ]
}"""

QUERY_EXPANSION_SYSTEM = """\
Generate diverse search queries to find evidence for or against a factual claim.
Respond with ONLY a JSON object:
{"queries": ["query1", "query2", "query3"]}"""


def _extract_json(text: str) -> dict:
    """Robustly parse JSON from LLM output — handles markdown fences and embedded JSON."""
    if not text:
        return {}
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


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class Verifier:
    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        cache: Optional[ClaimCache] = None,
        reranker: Optional[CrossEncoderReranker] = None,
    ) -> None:
        self._kb = knowledge_base
        self._cache = cache or ClaimCache()
        self._reranker = reranker  # None is valid — guarded at call site
        self._settings = get_settings()
        s = self._settings

        self._client = AsyncOpenAI(
            base_url=s.ollama_base_url,
            api_key=s.ollama_api_key,
            timeout=s.request_timeout,  # configurable timeout; defaults to 8 min for slow model loads
        )

        # Anthropic fallback client
        self._anthropic_client = None
        if s.llm_provider == "anthropic":
            try:
                import anthropic as _anthropic
                self._anthropic_client = _anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
            except ImportError:
                pass

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def verify(
        self, claims: List[ExtractedClaim]
    ) -> Tuple[List[VerifiedClaim], List[RetrievalMetadata]]:
        """Verify all claims. Returns (verified_claims, retrieval_metadata_list). Never raises."""
        if not claims:
            return [], []

        s = self._settings

        # Step 1: Check cache
        results: List[Optional[VerifiedClaim]] = [None] * len(claims)
        meta_list: List[Optional[RetrievalMetadata]] = [None] * len(claims)
        uncached_indices: List[int] = []

        if s.cache_enabled:
            for i, claim in enumerate(claims):
                cached = self._cache.get(claim.normalized)
                if cached is not None:
                    results[i] = cached
                    meta_list[i] = RetrievalMetadata(claim_id=claim.id, cache_hit=True)
                    logger.debug("[cache hit] %s", claim.normalized[:60])
                else:
                    uncached_indices.append(i)
        else:
            uncached_indices = list(range(len(claims)))

        if not uncached_indices:
            return [r for r in results], [m for m in meta_list]  # type: ignore

        # Step 2: Expand queries
        uncached_claims = [claims[i] for i in uncached_indices]
        expansions = await asyncio.gather(*[self._expand_queries(c) for c in uncached_claims])

        # Step 3: Retrieve + re-rank docs
        retrieval_tasks = [
            self._retrieve_and_rerank(claim, queries)
            for claim, queries in zip(uncached_claims, expansions)
        ]
        retrieval_results: List[Tuple[List[Dict], RetrievalMetadata]] = await asyncio.gather(*retrieval_tasks)
        claim_docs = [r[0] for r in retrieval_results]
        claim_metas = [r[1] for r in retrieval_results]

        # Step 4: Separate critical/high for ensemble (if enabled)
        if s.ensemble_for_critical:
            ensemble_idx = [
                i for i, c in enumerate(uncached_claims)
                if c.stakes in (ClaimStakes.CRITICAL, ClaimStakes.HIGH)
            ]
            standard_idx = [i for i in range(len(uncached_claims)) if i not in set(ensemble_idx)]
        else:
            ensemble_idx = []
            standard_idx = list(range(len(uncached_claims)))

        verified_uncached: List[Optional[VerifiedClaim]] = [None] * len(uncached_claims)

        if standard_idx:
            std_claims = [uncached_claims[i] for i in standard_idx]
            std_docs = [claim_docs[i] for i in standard_idx]
            std_verified = await self._batch_verify(std_claims, std_docs, s.verifier_model)
            for local_i, global_i in enumerate(standard_idx):
                verified_uncached[global_i] = std_verified[local_i]

        if ensemble_idx:
            ens_claims = [uncached_claims[i] for i in ensemble_idx]
            ens_docs = [claim_docs[i] for i in ensemble_idx]
            ens_verified = await self._ensemble_verify(ens_claims, ens_docs)
            for local_i, global_i in enumerate(ensemble_idx):
                verified_uncached[global_i] = ens_verified[local_i]
                claim_metas[global_i].ensemble_used = True

        # Step 5: Cache + merge results
        for local_i, global_i in enumerate(uncached_indices):
            vc = verified_uncached[local_i]
            if vc is None:
                vc = self._make_unverifiable(claims[global_i], "Verification produced no result")
            results[global_i] = vc
            meta_list[global_i] = claim_metas[local_i]
            if s.cache_enabled:
                self._cache.set(claims[global_i].normalized, vc)

        return [r for r in results], [m for m in meta_list]  # type: ignore

    # ------------------------------------------------------------------
    # Query expansion
    # ------------------------------------------------------------------

    async def _expand_queries(self, claim: ExtractedClaim) -> List[str]:
        s = self._settings
        if not s.multi_query_enabled and not s.hyde_enabled:
            return [claim.normalized]

        try:
            response = await self._client.chat.completions.create(
                model=s.extractor_model,
                messages=[
                    {"role": "system", "content": QUERY_EXPANSION_SYSTEM},
                    {"role": "user", "content": (
                        f"Claim: {claim.normalized}\n"
                        f"Type: {claim.claim_type.value}, Stakes: {claim.stakes.value}\n\n"
                        f"Generate {s.multi_query_count} search queries to find evidence."
                    )},
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""
            data = _extract_json(content)
            queries = data.get("queries", [])
            if queries:
                all_q = [claim.normalized] + [q for q in queries if q.strip()]
                seen, deduped = set(), []
                for q in all_q:
                    if q not in seen:
                        seen.add(q)
                        deduped.append(q)
                return deduped[:s.multi_query_count + 2]
        except Exception as exc:
            logger.debug("Query expansion failed: %s", exc)

        return [claim.normalized]

    # ------------------------------------------------------------------
    # Retrieval + re-ranking
    # ------------------------------------------------------------------

    async def _retrieve_and_rerank(
        self,
        claim: ExtractedClaim,
        queries: List[str],
    ) -> Tuple[List[Dict], RetrievalMetadata]:
        s = self._settings
        tasks = [self._kb.query_async(q, n_results=s.kb_top_k) for q in queries]
        all_results: List[List[Dict]] = await asyncio.gather(*tasks)

        seen_excerpts: set = set()
        merged: List[Dict] = []
        for hits in all_results:
            for hit in hits:
                key = hit["excerpt"][:120]
                if key not in seen_excerpts:
                    seen_excerpts.add(key)
                    merged.append(hit)

        total_retrieved = len(merged)

        if s.reranker_enabled and merged and self._reranker is not None:
            merged = await self._reranker.rerank_async(claim.normalized, merged, top_k=max(s.reranker_top_k, 3))

        meta = RetrievalMetadata(
            claim_id=claim.id,
            query_variants=queries,
            total_retrieved=total_retrieved,
            total_after_rerank=len(merged),
            cache_hit=False,
            ensemble_used=False,
        )
        return merged, meta

    # ------------------------------------------------------------------
    # Batch LLM verification
    # ------------------------------------------------------------------

    async def _batch_verify(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
        model: str,
    ) -> List[VerifiedClaim]:
        if not claims:
            return []

        claims_text = "\n".join(
            f"Claim {i}: {c.normalized}  [type={c.claim_type.value}, stakes={c.stakes.value}]"
            for i, c in enumerate(claims)
        )

        # Deduplicate source chunks
        seen: Dict[str, int] = {}
        sources: List[str] = []
        claim_src_map: List[List[int]] = []

        for docs in claim_docs:
            indices: List[int] = []
            for doc in docs:
                key = doc["excerpt"][:120]
                if key not in seen:
                    seen[key] = len(sources)
                    rerank_note = f" [rerank={doc['rerank_score']:.2f}]" if doc.get("rerank_score") is not None else ""
                    sources.append(
                        f"[Source {len(sources)}: {doc['source']}{rerank_note}]\n"
                        f"{doc['excerpt'][:450]}"
                    )
                indices.append(seen[key])
            claim_src_map.append(indices)

        if not sources:
            return self._all_unverifiable(claims, "No relevant documents found in knowledge base.")

        mapping = "\n".join(
            f"Claim {i} sources: {claim_src_map[i] or 'none'}"
            for i in range(len(claims))
        )
        user_content = (
            f"CLAIMS TO VERIFY:\n{claims_text}\n\n"
            f"SOURCE MAPPING (which sources apply to each claim):\n{mapping}\n\n"
            f"REFERENCE SOURCES:\n" + "\n\n".join(sources) +
            "\n\nReturn ONLY the JSON verification results."
        )

        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": VERIFIER_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            data = _extract_json(content)
            raw_results = data.get("results", [])
            if raw_results:
                return self._build_results(claims, claim_docs, raw_results)
        except Exception as exc:
            logger.error("Verifier error (%s): %s", model, exc)

        return self._all_unverifiable(claims, "Verification failed.")

    # ------------------------------------------------------------------
    # Ensemble
    # ------------------------------------------------------------------

    async def _ensemble_verify(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
    ) -> List[VerifiedClaim]:
        s = self._settings
        haiku_task = self._batch_verify(claims, claim_docs, s.verifier_model)
        sonnet_task = self._batch_verify(claims, claim_docs, s.ensemble_model)
        haiku_results, sonnet_results = await asyncio.gather(haiku_task, sonnet_task)

        merged: List[VerifiedClaim] = []
        status_priority = {
            VerificationStatus.CONTRADICTED: 0,
            VerificationStatus.UNVERIFIABLE: 1,
            VerificationStatus.PARTIALLY_SUPPORTED: 2,
            VerificationStatus.VERIFIED: 3,
        }
        for h, s_res in zip(haiku_results, sonnet_results):
            stricter = (
                h.status if status_priority[h.status] <= status_priority[s_res.status]
                else s_res.status
            )
            avg_conf = round((h.confidence + s_res.confidence) / 2, 3)
            merged.append(VerifiedClaim(
                claim=h.claim,
                status=stricter,
                confidence=avg_conf,
                supporting_docs=h.supporting_docs or s_res.supporting_docs,
                contradiction_reason=h.contradiction_reason or s_res.contradiction_reason,
                verification_reasoning=s_res.verification_reasoning or h.verification_reasoning,
                key_evidence=s_res.key_evidence or h.key_evidence,
            ))
        return merged

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_results(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
        raw_results: list,
    ) -> List[VerifiedClaim]:
        result_map: Dict[int, dict] = {r.get("claim_index", -1): r for r in raw_results}
        verified: List[VerifiedClaim] = []

        for i, claim in enumerate(claims):
            r = result_map.get(i, {})
            status = VerificationStatus.UNVERIFIABLE
            try:
                status = VerificationStatus(r.get("status", "unverifiable"))
            except ValueError:
                pass

            confidence = max(0.0, min(1.0, float(r.get("confidence", 0.3))))
            supporting = [
                SupportingDocument(
                    doc_id=d["doc_id"],
                    source=d["source"],
                    excerpt=d["excerpt"][:300],
                    relevance_score=d["relevance_score"],
                    rerank_score=d.get("rerank_score"),
                )
                for d in claim_docs[i]
            ]
            verified.append(VerifiedClaim(
                claim=claim,
                status=status,
                confidence=confidence,
                supporting_docs=supporting,
                verification_reasoning=r.get("reasoning", ""),
                key_evidence=r.get("key_evidence", ""),
                contradiction_reason=r.get("contradiction_reason") or None,
            ))
        return verified

    @staticmethod
    def _make_unverifiable(claim: ExtractedClaim, reason: str) -> VerifiedClaim:
        return VerifiedClaim(
            claim=claim,
            status=VerificationStatus.UNVERIFIABLE,
            confidence=0.3,
            verification_reasoning=reason,
        )

    @staticmethod
    def _all_unverifiable(claims: List[ExtractedClaim], reason: str) -> List[VerifiedClaim]:
        return [Verifier._make_unverifiable(c, reason) for c in claims]
