"""
Advanced Verifier — cross-checks extracted claims against the knowledge base.

Uses a local Ollama LLM (free, no API key required) for verification.
Supports: multi-query expansion, cross-encoder re-ranking, claim cache, ensemble.
"""
import asyncio
import json
import logging
import random
import re
import time
from typing import Dict, List, Optional, Tuple, Callable, Coroutine, Any

from openai import AsyncOpenAI

from .cache import ClaimCache
from .config import get_settings
from .knowledge_base import KnowledgeBase
from .nli_scorer import get_nli_scorer
from .models import (
    ClaimStakes,
    ClaimType,
    ExtractedClaim,
    RetrievalMetadata,
    SupportingDocument,
    VerificationStatus,
    VerifiedClaim,
)
from .reranker import CrossEncoderReranker
from .source_credibility import score_documents, validate_contradiction
from .web_search import web_search_structured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM = """\
You are a precise fact-checker. Verify each claim against the provided source documents.

Status definitions:
- verified: The claim is directly and clearly supported by the source text. Use confidence 0.75-1.00.
- contradicted: The source explicitly states something that conflicts with the claim. Use confidence 0.00-0.35.
- partially_supported: Sources mention the topic but only partially confirm the claim, or only some parts are supported. Use confidence 0.40-0.70.
- unverifiable: The sources do not contain relevant information about this claim. Use confidence 0.20-0.40.

Confidence calibration:
- 0.92-1.00: Claim matches source almost word-for-word
- 0.80-0.91: Claim is clearly and directly supported
- 0.65-0.79: Claim is mostly supported with minor gaps
- 0.45-0.64: Partial or indirect support only
- 0.20-0.44: Contradicted or no evidence found

Rules:
- key_evidence MUST be an exact verbatim quote from the source (max 150 chars). Do NOT paraphrase.
- If no source mentions the claim, use status=unverifiable — NOT contradicted.
- contradicted requires positive evidence in the source that DIRECTLY conflicts.
- reasoning should be 1-2 sentences explaining your decision.
- Output ONLY raw JSON starting with { — no markdown, no code fences, no prose before or after.

Output format:
{"results":[{"claim_index":0,"status":"verified","confidence":0.88,"reasoning":"The source directly states this fact.","key_evidence":"exact quote from source here","contradiction_reason":""}]}"""

VERIFIER_SYSTEM_SIMPLE = """\
You are a fact-checker. Verify the claim against the sources. Output ONLY JSON starting with {
Status: verified (source supports it) | contradicted (source conflicts) | partially_supported (partial match) | unverifiable (not mentioned)
{"status":"verified","confidence":0.85,"reasoning":"1-2 sentence reason","key_evidence":"exact quote","contradiction_reason":""}"""

QUERY_EXPANSION_SYSTEM = """\
Generate diverse search queries to find evidence for a factual claim in a knowledge base.
Vary phrasing — use different keywords, synonyms, and angles to maximise recall.
Output ONLY JSON starting with {
{"queries":["specific query 1","broader query 2"]}"""


def _extract_json(text: str) -> dict:
    """Robustly parse JSON from LLM output — handles markdown, prose, truncation."""
    if not text:
        return {}

    # Strip markdown fences and leading prose
    text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find outermost {...} block
    start = text.find("{")
    if start != -1:
        # Try progressively smaller substrings (handles truncated JSON)
        for end in range(len(text), start, -1):
            candidate = text[start:end]
            if not candidate.endswith("}"):
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # Last resort: regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.debug("JSON extraction failed. Raw LLM output: %s", text[:300])
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

        # Route primary client by provider
        if s.llm_provider == "nvidia_nim":
            self._client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
        elif s.llm_provider == "together":
            self._client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
        else:
            self._client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key, timeout=s.request_timeout)
        self._ollama_request_extra: dict = {}

        # NLI scorer — DeBERTa-v3, GPU-accelerated, used as fast primary verification
        self._nli = get_nli_scorer() if s.nli_enabled else None

        # Anthropic native client — used when llm_provider=anthropic
        self._anthropic_client = None
        if s.llm_provider == "anthropic":
            try:
                import anthropic as _anthropic  # noqa: PLC0415
                self._anthropic_client = _anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
            except ImportError:
                logger.warning("anthropic package not installed; falling back to Ollama client")

        # Fallback client: Together AI when primary=anthropic/nvidia_nim, NVIDIA NIM when primary=together
        self._fallback_client = None
        if s.llm_provider == "together" and s.nvidia_nim_api_key:
            self._fallback_client = AsyncOpenAI(base_url=s.nvidia_nim_base_url, api_key=s.nvidia_nim_api_key, timeout=s.request_timeout)
            logger.info("NVIDIA NIM fallback client ready for verifier")
        elif s.fallback_enabled and s.together_api_key and s.together_api_key not in ("", "your-together-api-key-here"):
            self._fallback_client = AsyncOpenAI(base_url=s.together_base_url, api_key=s.together_api_key, timeout=s.request_timeout)
            logger.info("Together AI fallback client ready for verifier")

    # ------------------------------------------------------------------
    # Unified LLM call (routes to Anthropic SDK or OpenAI-compatible)
    # ------------------------------------------------------------------

    async def _llm_call(
        self,
        model: str,
        messages: List[Dict],
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_fmt: bool = True,
        timeout: float = 90.0,
    ) -> str:
        """Send a chat request to whichever provider is configured. Returns raw text.
        Retries up to 3 times with exponential backoff for transient errors."""
        s = self._settings
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                if s.llm_provider == "anthropic" and self._anthropic_client is not None:
                    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
                    user_msgs = [m for m in messages if m["role"] != "system"]
                    resp = await asyncio.wait_for(
                        self._anthropic_client.messages.create(
                            model=model,
                            system=system,
                            messages=user_msgs,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        ),
                        timeout=timeout,
                    )
                    return next(
                        (block.text for block in resp.content if hasattr(block, "text")), ""
                    )

                # OpenAI-compatible path (Ollama / NVIDIA NIM)
                # json_object format hangs on NVIDIA NIM — disable it there
                use_json_fmt = json_fmt and s.llm_provider != "nvidia_nim"
                create_kwargs: dict = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    **self._ollama_request_extra,
                }
                if use_json_fmt:
                    create_kwargs["response_format"] = {"type": "json_object"}
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(**create_kwargs),
                    timeout=timeout,
                )
                return response.choices[0].message.content or ""

            except (asyncio.TimeoutError, Exception) as exc:
                exc_str = str(exc).lower()
                # Don't retry auth errors
                if any(kw in exc_str for kw in ("401", "403", "unauthorized", "forbidden", "api key")):
                    raise
                # Rate-limit or overload: try Together AI fallback immediately
                is_rate_limit = any(kw in exc_str for kw in ("429", "rate limit", "rate_limit", "overloaded", "529", "503", "credit balance", "billing", "insufficient", "402", "quota"))
                if is_rate_limit and self._fallback_client is not None:
                    logger.warning("Primary LLM rate-limited — switching to fallback")
                    try:
                        s = self._settings
                        # When primary=together, fallback is NIM (use NIM model names)
                        if s.llm_provider == "together":
                            fallback_model = "meta/llama-3.3-70b-instruct" if model == s.verifier_model else "meta/llama-3.1-8b-instruct"
                        else:
                            fallback_model = (
                                s.together_verifier_model if model == s.verifier_model
                                else s.together_extractor_model
                            )
                        response = await asyncio.wait_for(
                            self._fallback_client.chat.completions.create(
                                model=fallback_model,
                                messages=messages,
                                temperature=temperature,
                            ),
                            timeout=timeout,
                        )
                        result = response.choices[0].message.content or ""
                        if result:
                            logger.info("Together AI fallback succeeded (model=%s)", fallback_model)
                            return result
                    except Exception as fb_exc:
                        logger.warning("Together AI fallback also failed: %s", fb_exc)
                if attempt == max_retries - 1:
                    raise
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                logger.debug(
                    "LLM call attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt + 1, max_retries, exc, delay,
                )
                await asyncio.sleep(delay)
        return ""  # unreachable — loop always raises on final attempt

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def verify(
        self, claims: List[ExtractedClaim]
    ) -> Tuple[List[VerifiedClaim], List[RetrievalMetadata]]:
        """Verify all claims. Delegates to verify_streaming with no progress callback."""
        return await self.verify_streaming(claims, progress_cb=None)

    async def verify_streaming(
        self,
        claims: List[ExtractedClaim],
        progress_cb: Optional[Callable[[str, dict], Coroutine[Any, Any, None]]] = None,
    ) -> Tuple[List[VerifiedClaim], List[RetrievalMetadata]]:
        """Verify claims with streaming progress updates. Returns (verified_claims, retrieval_metadata_list). Never raises."""
        if not claims:
            return [], []

        s = self._settings

        # Step 1: Check cache
        results: List[Optional[VerifiedClaim]] = [None] * len(claims)
        meta_list: List[Optional[RetrievalMetadata]] = [None] * len(claims)
        uncached_indices: List[int] = []

        _NON_FACTUAL = {ClaimType.OPINION, ClaimType.PREDICTION, ClaimType.CREATIVE}

        if s.cache_enabled:
            for i, claim in enumerate(claims):
                # Non-factual claims skip verification entirely — auto-pass them
                if claim.claim_type in _NON_FACTUAL:
                    results[i] = VerifiedClaim(
                        claim=claim,
                        status=VerificationStatus.VERIFIED,
                        confidence=1.0,
                        verification_reasoning=f"Auto-pass: {claim.claim_type.value} content is not verifiable",
                    )
                    meta_list[i] = RetrievalMetadata(claim_id=claim.id, cache_hit=False)
                    continue
                cached = await self._cache.get(claim.normalized)
                if cached is not None:
                    results[i] = cached
                    meta_list[i] = RetrievalMetadata(claim_id=claim.id, cache_hit=True)
                    logger.debug("[cache hit] %s", claim.normalized[:60])
                    if progress_cb:
                        await progress_cb("claim_verified", {
                            "claim": claim.model_dump(),
                            "status": cached.status.value,
                            "confidence": cached.confidence,
                            "cache_hit": True,
                            "ensemble_used": False,
                            "key_evidence": cached.key_evidence,
                        })
                else:
                    uncached_indices.append(i)
        else:
            for i, claim in enumerate(claims):
                if claim.claim_type in _NON_FACTUAL:
                    results[i] = VerifiedClaim(
                        claim=claim,
                        status=VerificationStatus.VERIFIED,
                        confidence=1.0,
                        verification_reasoning=f"Auto-pass: {claim.claim_type.value} content is not verifiable",
                    )
                    meta_list[i] = RetrievalMetadata(claim_id=claim.id, cache_hit=False)
                else:
                    uncached_indices.append(i)

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

        # Non-streaming: verify all claims in one batch (single LLM call = faster)
        # Streaming: one claim at a time for live progress updates
        all_indices = standard_idx + ensemble_idx
        batch_size = s.streaming_batch_size if progress_cb is not None else max(len(all_indices), 1)
        
        for i in range(0, len(all_indices), batch_size):
            batch_indices = all_indices[i:i + batch_size]
            
            # Process batch
            batch_claims = [uncached_claims[j] for j in batch_indices]
            batch_docs = [claim_docs[j] for j in batch_indices]
            
            # Determine which model to use for this batch
            if any(j in ensemble_idx for j in batch_indices):
                # Use ensemble for batches containing critical/high stakes claims
                batch_verified = await self._ensemble_verify(batch_claims, batch_docs)
                for local_i, global_i in enumerate(batch_indices):
                    verified_uncached[global_i] = batch_verified[local_i]
                    claim_metas[global_i].ensemble_used = True
            else:
                # Use standard verification for other batches
                batch_verified = await self._batch_verify(batch_claims, batch_docs, s.verifier_model)
                for local_i, global_i in enumerate(batch_indices):
                    verified_uncached[global_i] = batch_verified[local_i]

            # Send progress updates for completed claims in this batch
            if progress_cb:
                for local_i, global_i in enumerate(batch_indices):
                    vc = verified_uncached[global_i]
                    if vc is not None:
                        await progress_cb("claim_verified", {
                            "claim": vc.claim.model_dump(),
                            "status": vc.status.value,
                            "confidence": vc.confidence,
                            "cache_hit": claim_metas[global_i].cache_hit,
                            "ensemble_used": claim_metas[global_i].ensemble_used,
                            "key_evidence": vc.key_evidence,
                        })
            
            # Throttle updates only when streaming to a client (no-op for non-streaming calls)
            if progress_cb is not None and i + batch_size < len(all_indices):
                await asyncio.sleep(s.streaming_claim_delay)

        # Step 5: Cache + merge results
        for local_i, global_i in enumerate(uncached_indices):
            vc = verified_uncached[local_i]
            if vc is None:
                vc = self._make_unverifiable(claims[global_i], "Verification produced no result")
            results[global_i] = vc
            meta_list[global_i] = claim_metas[local_i]
            if s.cache_enabled:
                await self._cache.set(claims[global_i].normalized, vc)

        return [r for r in results], [m for m in meta_list]  # type: ignore

    # ------------------------------------------------------------------
    # Query expansion
    # ------------------------------------------------------------------

    async def _expand_queries(self, claim: ExtractedClaim) -> List[str]:
        s = self._settings
        if not s.multi_query_enabled and not s.hyde_enabled:
            return [claim.normalized]
        # Skip LLM expansion for low/medium stakes — direct KB lookup is fast enough.
        # Only expand for critical/high stakes where thoroughness justifies the LLM call.
        if claim.stakes.value in ("low", "medium") and not s.hyde_enabled:
            return [claim.normalized]

        try:
            content = await self._llm_call(
                model=s.extractor_model,
                messages=[
                    {"role": "system", "content": QUERY_EXPANSION_SYSTEM},
                    {"role": "user", "content": (
                        f"Claim: {claim.normalized}\n"
                        f"Type: {claim.claim_type.value}, Stakes: {claim.stakes.value}\n\n"
                        f"Generate {s.multi_query_count} search queries to find evidence."
                    )},
                ],
                json_fmt=True,
                timeout=30.0,
            )
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
        n_results = s.reranker_candidate_count if s.reranker_enabled else s.kb_top_k
        tasks = [self._kb.query_async(q, n_results=n_results) for q in queries]
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

        # Web-RAG fallback: if KB has no good evidence, query the live web
        if s.web_rag_enabled:
            top_kb_score = merged[0]["relevance_score"] if merged else 0.0
            if top_kb_score < s.web_rag_kb_threshold:
                logger.info(
                    "[Web-RAG] KB top score %.2f < %.2f for claim: %s — querying web",
                    top_kb_score, s.web_rag_kb_threshold, claim.normalized[:60],
                )
                web_docs = await web_search_structured(claim.normalized, max_results=3)
                for wd in web_docs:
                    key = wd["excerpt"][:120]
                    if key not in seen_excerpts:
                        seen_excerpts.add(key)
                        merged.append(wd)
                if web_docs:
                    total_retrieved += len(web_docs)

        # Score source credibility and blend into relevance scores
        merged = score_documents(merged)

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

    async def _nli_verify(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
    ) -> List[VerifiedClaim]:
        """Fast DeBERTa-v3 NLI verification. Returns results only when confidence is high enough."""
        s = self._settings
        if self._nli is None:
            return [None] * len(claims)  # type: ignore

        results: List[VerifiedClaim | None] = []
        for claim, docs in zip(claims, claim_docs):
            if not docs:
                results.append(None)
                continue
            excerpts = [d["excerpt"] for d in docs[:5]]
            conf, status = self._nli.best_score(claim.normalized, excerpts)
            if conf >= s.nli_confidence_threshold:
                best_doc = docs[0] if docs else {}
                results.append(VerifiedClaim(
                    claim=claim,
                    status=VerificationStatus(status),
                    confidence=round(conf, 3),
                    supporting_docs=[
                        SupportingDocument(
                            doc_id=d.get("doc_id", "nli"),
                            source=d.get("source", "NLI"),
                            excerpt=d.get("excerpt", "")[:300],
                            relevance_score=d.get("relevance_score", 0.0),
                            credibility_score=d.get("credibility_score"),
                        )
                        for d in docs[:3]
                    ],
                    verification_reasoning=f"DeBERTa-v3 NLI: {status} (confidence {conf:.2f})",
                    key_evidence=docs[0]["excerpt"][:150] if docs else "",
                ))
            else:
                results.append(None)  # Fall through to LLM
        return results  # type: ignore

    async def _batch_verify(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
        model: str,
    ) -> List[VerifiedClaim]:
        if not claims:
            return []

        # Fast path: DeBERTa-v3 NLI (GPU) — use when confidence is high
        s = self._settings
        if s.nli_enabled and self._nli is not None:
            nli_results = await self._nli_verify(claims, claim_docs)
            high_conf_indices = [i for i, r in enumerate(nli_results) if r is not None]
            llm_indices = [i for i, r in enumerate(nli_results) if r is None]

            if llm_indices:
                llm_claims = [claims[i] for i in llm_indices]
                llm_docs = [claim_docs[i] for i in llm_indices]
                llm_results = await self._batch_verify_llm(llm_claims, llm_docs, model)
                for local_i, global_i in enumerate(llm_indices):
                    nli_results[global_i] = llm_results[local_i]

            logger.info(
                "NLI fast-path: %d/%d claims resolved (LLM used for %d)",
                len(high_conf_indices), len(claims), len(llm_indices),
            )
            return [r for r in nli_results]  # type: ignore

        return await self._batch_verify_llm(claims, claim_docs, model)

    async def _batch_verify_llm(
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
            f"SOURCE MAPPING:\n{mapping}\n\n"
            f"SOURCES:\n" + "\n\n".join(sources) +
            "\n\nOutput ONLY JSON starting with {\"results\":"
        )

        content = ""
        try:
            content = await self._llm_call(
                model=model,
                messages=[
                    {"role": "system", "content": VERIFIER_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=2048,
                json_fmt=True,
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Verifier LLM call timed out after 90s — returning unverifiable")
            return self._all_unverifiable(claims, "LLM verification timed out (90s)")
        except Exception as exc:
            logger.error("Verifier LLM call failed (%s): %s", model, exc)
            return self._all_unverifiable(claims, f"LLM error: {exc}")

        data = _extract_json(content)
        raw_results = data.get("results", [])
        if raw_results:
            return self._build_results(claims, claim_docs, raw_results)

        # Attempt 2: simplified per-claim prompt when batch fails
        logger.warning("Batch verify returned no results — retrying with simplified prompt. Raw: %s", content[:200])
        return await self._simple_verify_fallback(claims, claim_docs, model)

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
            docs_i = claim_docs[i]

            # Contradiction cross-validation: require ≥2 independent domains.
            # A single low-trust source cannot mark a claim as CONTRADICTED.
            if status == VerificationStatus.CONTRADICTED:
                accepted, avg_cred = validate_contradiction(docs_i, threshold=2)
                if not accepted:
                    status = VerificationStatus.PARTIALLY_SUPPORTED
                    confidence = min(confidence, 0.55)
                else:
                    # Blend LLM confidence with source credibility
                    confidence = round(0.7 * confidence + 0.3 * avg_cred, 3)

            supporting = [
                SupportingDocument(
                    doc_id=d["doc_id"],
                    source=d["source"],
                    excerpt=d["excerpt"][:300],
                    relevance_score=d["relevance_score"],
                    rerank_score=d.get("rerank_score"),
                    credibility_score=d.get("credibility_score"),
                )
                for d in docs_i
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

    async def _simple_verify_fallback(
        self,
        claims: List[ExtractedClaim],
        claim_docs: List[List[Dict]],
        model: str,
    ) -> List[VerifiedClaim]:
        """Verify one claim at a time with a minimal prompt — used when batch fails."""
        results: List[VerifiedClaim] = []
        for i, claim in enumerate(claims):
            docs = claim_docs[i]
            if not docs:
                results.append(self._make_unverifiable(claim, "No source documents found."))
                continue

            source_text = "\n\n".join(
                f"[{j}] {d['source']}: {d['excerpt'][:300]}"
                for j, d in enumerate(docs[:3])
            )
            prompt = (
                f"Claim: {claim.normalized}\n\n"
                f"Sources:\n{source_text}\n\n"
                f'Output JSON: {{"status":"verified|contradicted|partially_supported|unverifiable","confidence":0.7,"reasoning":"reason","key_evidence":"quote"}}'
            )
            try:
                content = await self._llm_call(
                    model=model,
                    messages=[
                        {"role": "system", "content": VERIFIER_SYSTEM_SIMPLE},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=200,
                    json_fmt=True,
                    timeout=30.0,
                )
                data = _extract_json(content)
                raw = [{"claim_index": 0, **data}] if data.get("status") else []
                if raw:
                    built = self._build_results([claim], [docs], raw)
                    results.append(built[0])
                    continue
            except Exception as exc:
                logger.debug("Simple verify fallback error for claim %d: %s", i, exc)
            results.append(self._make_unverifiable(claim, "Verification failed after retry."))
        return results

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
