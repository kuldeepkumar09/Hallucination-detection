"""
FastAPI proxy server — advanced edition.

New in v2:
  • True SSE streaming: buffers upstream stream, verifies, re-streams annotated chunks
  • OpenAI /v1/chat/completions compatibility (converts to/from Anthropic format)
  • Configurable timeout (settings.request_timeout)
  • /cache/stats and /cache/clear endpoints
  • Improved audit injection with retrieval metadata
"""
import asyncio
import collections
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .audit_trail import AuditTrail
from .config import get_settings
from .pipeline import HallucinationDetectionPipeline

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Rate limiting — Redis sliding window (ZADD/ZREMRANGEBYSCORE) with
# in-memory deque fallback when Redis is unavailable.
# Redis version is distributed: works correctly across multiple workers/processes.
# ---------------------------------------------------------------------------

_RATE_WINDOWS: Dict[str, collections.deque] = collections.defaultdict(
    lambda: collections.deque()
)
_rate_redis = None   # set in lifespan after settings are loaded


def _get_api_key_from_request(request: Request) -> Optional[str]:
    """Extract API key from request headers."""
    return request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip() or None


async def verify_api_key(request: Request) -> None:
    """Read-level auth — grants access to /verify, /audit, /kb/stats, /health.
    Accepts both read keys (api_key) and admin keys (admin_key).
    If both are empty, auth is disabled (dev mode).
    """
    all_keys = settings.valid_api_keys | settings.valid_admin_keys
    if not all_keys:
        return  # Auth disabled in dev mode
    api_key = _get_api_key_from_request(request)
    if not api_key or api_key not in all_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def verify_admin_key(request: Request) -> None:
    """Admin-level auth — required for /kb/ingest, /kb/delete, /cache/clear.
    Only admin keys are accepted. Falls back to no-auth if admin_key is empty.
    """
    admin_keys = settings.valid_admin_keys
    if not admin_keys:
        return  # Admin auth disabled — fall back to read-key check
    api_key = _get_api_key_from_request(request)
    if not api_key or api_key not in admin_keys:
        raise HTTPException(status_code=403, detail="Admin key required")


async def _check_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    api_key = _get_api_key_from_request(request)
    client_id = api_key if api_key else (request.client.host if request.client else "unknown")
    limit = settings.rate_limit_requests
    window = settings.rate_limit_window

    # ── Redis sliding-window (distributed, works across multiple workers) ──
    if _rate_redis is not None:
        try:
            now_ms = int(time.time() * 1000)
            rkey = f"rl::{client_id}"
            pipe = _rate_redis.pipeline()
            # Remove entries outside the current window
            await pipe.zremrangebyscore(rkey, 0, now_ms - window * 1000)
            # Count remaining entries
            await pipe.zcard(rkey)
            # Add this request
            await pipe.zadd(rkey, {str(now_ms): now_ms})
            # Auto-expire the key after 2× window (housekeeping)
            await pipe.expire(rkey, window * 2)
            results = await pipe.execute()
            count = results[1]   # zcard result (before this request)
            if count >= limit:
                raise HTTPException(429, f"Rate limit exceeded — max {limit} req/{window}s")
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("Redis rate limit check failed, falling back to in-memory: %s", exc)

    # ── In-memory fallback (single-process only) ───────────────────────────
    now = time.monotonic()
    dq = _RATE_WINDOWS[client_id]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(429, f"Rate limit exceeded — max {limit} req/{window}s")
    dq.append(now)
    if len(_RATE_WINDOWS) > 10_000:
        stale = [k for k, v in list(_RATE_WINDOWS.items()) if not v]
        for k in stale:
            _RATE_WINDOWS.pop(k, None)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_ALLOWED_URL_SCHEMES = {"http", "https"}
_MAX_TEXT_LEN = 50_000

def _validate_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in _ALLOWED_URL_SCHEMES:
        raise HTTPException(400, f"URL scheme '{p.scheme}' not allowed. Use http or https.")
    if not p.netloc:
        raise HTTPException(400, "Invalid URL — missing hostname.")

def _validate_text_length(text: str, field: str = "text") -> None:
    if len(text) > _MAX_TEXT_LEN:
        raise HTTPException(400, f"'{field}' exceeds {_MAX_TEXT_LEN:,} character limit ({len(text):,} chars).")

# ---------------------------------------------------------------------------
# Audit entry flattener
# ---------------------------------------------------------------------------

def _flatten_audit_entry(entry: dict) -> dict:
    """Convert nested ClaimDecision structure → flat claim dicts for frontend."""
    claims_raw = entry.get("claims", [])
    flat: List[dict] = []
    for c in claims_raw:
        if not isinstance(c, dict):
            continue
        vc = c.get("verified_claim", {}) or {}
        claim = vc.get("claim", {}) or {}
        flat.append({
            "id": claim.get("id") or c.get("id"),
            "text": claim.get("text") or c.get("text", ""),
            "type": claim.get("claim_type") or c.get("type", "entity"),
            "stakes": claim.get("stakes") or c.get("stakes", "medium"),
            "category": claim.get("category") or c.get("category", "GENERAL"),
            "status": vc.get("status") or c.get("status", "unverifiable"),
            "confidence": vc.get("confidence") if vc else c.get("confidence", 0.3),
            "action": c.get("action", "flag"),
            "annotation": c.get("annotation", ""),
            "key_evidence": vc.get("key_evidence", "") if vc else "",
            "reasoning": vc.get("verification_reasoning", "") if vc else "",
        })
    result = {k: v for k, v in entry.items() if k != "claims"}
    result["claims"] = flat
    return result

# ---------------------------------------------------------------------------
# App + lifecycle
# ---------------------------------------------------------------------------

_pipeline: Optional[HallucinationDetectionPipeline] = None
_audit: Optional[AuditTrail] = None
_http_client: Optional[httpx.AsyncClient] = None


async def _warmup_ollama() -> None:
    """Send a minimal request to Ollama so the model is loaded before the first user request."""
    try:
        from openai import AsyncOpenAI
        s = get_settings()
        if s.llm_provider != "ollama":
            return
        client = AsyncOpenAI(base_url=s.ollama_base_url, api_key=s.ollama_api_key, timeout=300.0)
        await client.chat.completions.create(
            model=s.extractor_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        logger.info("Ollama model warm-up complete (%s)", s.extractor_model)
    except Exception as exc:
        logger.warning("Ollama warm-up failed (model will load on first request): %s", exc)


_seed_status: Dict[str, Any] = {"running": False, "done": False, "progress": 0, "total": 0, "failed": []}


async def _seed_wikipedia_if_empty() -> None:
    """Auto-ingest foundational Wikipedia articles when KB is nearly empty.
    Controlled by WIKI_AUTO_SEED_ENABLED and WIKI_AUTO_SEED_THRESHOLD in config.
    Progress is exposed via the /status/seed endpoint."""
    global _seed_status
    s = get_settings()
    if not s.wiki_auto_seed_enabled:
        return
    try:
        kb = _pipeline.knowledge_base
        if kb.stats()["total_chunks"] >= s.wiki_auto_seed_threshold:
            return
        topics = s.wiki_seed_topics_list
        logger.info("[Startup] KB has < %d chunks — auto-seeding %d Wikipedia topics…",
                    s.wiki_auto_seed_threshold, len(topics))
        _seed_status = {"running": True, "done": False, "progress": 0, "total": len(topics), "failed": []}
        from .wikipedia_ingest import ingest_from_wikipedia  # noqa: PLC0415
        for i, topic in enumerate(topics):
            try:
                chunks = await asyncio.to_thread(ingest_from_wikipedia, topic, "en", kb, "summary")
                logger.info("[Startup] Wikipedia '%s': %d chunks", topic, chunks)
            except Exception as exc:
                logger.warning("[Startup] Wikipedia '%s' failed: %s", topic, exc)
                _seed_status["failed"].append(topic)
            _seed_status["progress"] = i + 1
        _seed_status["running"] = False
        _seed_status["done"] = True
        logger.info("[Startup] Wikipedia auto-seed complete (%d topics, %d failed)",
                    len(topics), len(_seed_status["failed"]))
    except Exception as exc:
        _seed_status["running"] = False
        logger.warning("[Startup] Wikipedia auto-seed failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _pipeline, _audit, _http_client, _rate_redis
    # Redis rate-limit client (separate connection pool from cache)
    if settings.rate_limit_redis_enabled and settings.redis_url:
        try:
            import redis.asyncio as aioredis  # noqa: PLC0415
            _rate_redis = aioredis.Redis.from_url(settings.redis_url, decode_responses=False)
            logger.info("Redis rate-limit client connected: %s", settings.redis_url)
        except Exception as exc:
            logger.warning("Redis rate-limit unavailable (%s) — using in-memory fallback", exc)
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    )
    logger.info("Initialising hallucination detection pipeline …")
    _pipeline = HallucinationDetectionPipeline()
    _audit = AuditTrail()
    logger.info(
        "Proxy ready on %s:%s  (provider: %s)",
        settings.proxy_host, settings.proxy_port, settings.llm_provider,
    )
    asyncio.create_task(_warmup_ollama())
    asyncio.create_task(_seed_wikipedia_if_empty())
    yield
    logger.info("Proxy shutting down")
    await _http_client.aclose()
    if _rate_redis is not None:
        await _rate_redis.aclose()


app = FastAPI(
    title="Hallucination Detection Proxy v3",
    description="Advanced real-time LLM hallucination detection middleware.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Serve React SPA from frontend/dist if it exists
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


def _pipeline_() -> HallucinationDetectionPipeline:
    if _pipeline is None:
        raise RuntimeError("Pipeline not initialised")
    return _pipeline


def _audit_() -> AuditTrail:
    if _audit is None:
        raise RuntimeError("AuditTrail not initialised")
    return _audit


# ---------------------------------------------------------------------------
# Monitoring endpoints
# ---------------------------------------------------------------------------

async def _check_llm_reachability(s) -> dict:
    """Lightweight LLM provider connectivity check (no tokens generated)."""
    try:
        if s.llm_provider == "ollama":
            # /api/tags is Ollama's fast metadata endpoint — no model load
            base = s.ollama_base_url.rstrip("/").removesuffix("/v1")
            resp = await _http_client.get(f"{base}/api/tags", timeout=3.0)
            if resp.status_code < 500:
                return {"ok": True}
            return {"ok": False, "error": f"Ollama returned HTTP {resp.status_code}"}
        if s.llm_provider == "nvidia_nim":
            if not s.nvidia_nim_api_key:
                return {"ok": False, "error": "NVIDIA_NIM_API_KEY not configured"}
            return {"ok": True}
        if s.llm_provider == "anthropic":
            if not s.anthropic_api_key:
                return {"ok": False, "error": "ANTHROPIC_API_KEY not configured"}
            return {"ok": True}
        if s.llm_provider == "together":
            if not s.together_api_key:
                return {"ok": False, "error": "TOGETHER_API_KEY not configured"}
            return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@app.get("/health")
async def health() -> JSONResponse:
    kb = _pipeline_().knowledge_base
    s = get_settings()
    llm_status = await _check_llm_reachability(s)
    llm_status["provider"] = s.llm_provider
    overall = "ok" if llm_status["ok"] else "degraded"
    if s.llm_provider == "together":
        fallback_ready = bool(s.nvidia_nim_api_key)
        fallback_provider = "NVIDIA NIM" if fallback_ready else "none"
        fallback_trigger = "Together AI 429/503 rate-limit"
    else:
        fallback_ready = bool(s.fallback_enabled and s.together_api_key and s.together_api_key != "your-together-api-key-here")
        fallback_provider = "Together AI" if fallback_ready else "none"
        fallback_trigger = f"{s.llm_provider.upper()} 429/503 rate-limit"
    return JSONResponse({
        "status": overall,
        "llm": llm_status,
        "fallback": {
            "enabled": fallback_ready,
            "provider": fallback_provider,
            "trigger": fallback_trigger,
        },
        "knowledge_base": kb.stats(),
        "cache": _pipeline_().cache_stats(),
        "audit": _audit_().get_stats(),
        "streaming": {
            "enabled": s.streaming_enabled,
            "batch_size": s.streaming_batch_size,
            "claim_delay": s.streaming_claim_delay,
        },
    })


@app.get("/audit/recent")
async def recent_audit(n: int = 10) -> JSONResponse:
    entries = _audit_().read_recent(n)
    return JSONResponse([_flatten_audit_entry(e) for e in entries])


@app.get("/audit/stats")
async def audit_stats() -> JSONResponse:
    return JSONResponse(_audit_().get_stats())


@app.get("/audit/rotation")
async def audit_rotation_info() -> JSONResponse:
    """Return information about audit log rotation status."""
    return JSONResponse(_audit_().get_rotation_info())


@app.get("/audit/stats/categories")
async def audit_stats_categories() -> JSONResponse:
    s = _audit_().get_stats()
    return JSONResponse(s.get("category_breakdown", {}))


@app.get("/audit/claim/{claim_id}")
async def get_claim_verification(claim_id: str) -> JSONResponse:
    """Retrieve verification result for a specific claim ID from audit trail."""
    # Search through recent audit entries to find the claim
    entries = _audit_().read_recent(100)  # Search last 100 entries
    
    for entry in entries:
        claims = entry.get("claims", [])
        for claim in claims:
            # Check if this claim matches the requested ID
            vc = claim.get("verified_claim", {}) or {}
            claim_obj = vc.get("claim", {}) or {}
            cid = claim_obj.get("id") or claim.get("id")
            
            if cid == claim_id:
                # Return the flattened claim with full verification details
                return JSONResponse({
                    "claim_id": claim_id,
                    "text": claim_obj.get("text", claim.get("text", "")),
                    "type": claim_obj.get("claim_type", claim.get("type", "entity")),
                    "stakes": claim_obj.get("stakes", claim.get("stakes", "medium")),
                    "category": claim_obj.get("category", claim.get("category", "GENERAL")),
                    "status": vc.get("status") or claim.get("status", "unverifiable"),
                    "confidence": vc.get("confidence") if vc else claim.get("confidence", 0.3),
                    "action": claim.get("action", "flag"),
                    "annotation": claim.get("annotation", ""),
                    "key_evidence": vc.get("key_evidence", "") if vc else "",
                    "reasoning": vc.get("verification_reasoning", "") if vc else "",
                    "request_id": entry.get("request_id", ""),
                    "timestamp": entry.get("timestamp", ""),
                })
    
    raise HTTPException(404, f"Claim with ID '{claim_id}' not found in recent audit entries")


@app.get("/kb/stats")
async def kb_stats() -> JSONResponse:
    return JSONResponse(_pipeline_().knowledge_base.stats())


@app.get("/kb/documents")
async def kb_documents(limit: int = 500) -> JSONResponse:
    # Web-only mode: no stored documents — evidence is fetched live per request
    return JSONResponse({"documents": [], "total": 0, "limit": limit, "mode": "web-only"})


@app.get("/status/seed")
async def seed_status() -> JSONResponse:
    """Return Wikipedia auto-seed progress (useful during first startup)."""
    s = get_settings()
    return JSONResponse({
        "enabled": s.wiki_auto_seed_enabled,
        "threshold": s.wiki_auto_seed_threshold,
        **_seed_status,
        "kb_chunks": _pipeline_().knowledge_base.stats()["total_chunks"],
    })


@app.get("/cache/stats")
async def cache_stats() -> JSONResponse:
    return JSONResponse(_pipeline_().cache_stats())


@app.post("/cache/clear", dependencies=[Depends(verify_admin_key)])
async def cache_clear() -> JSONResponse:
    await _pipeline_().invalidate_cache()
    return JSONResponse({"status": "ok", "message": "Cache cleared"})


# ---------------------------------------------------------------------------
# Benchmark evaluation endpoint
# ---------------------------------------------------------------------------

@app.post("/evaluate", dependencies=[Depends(verify_api_key)])
async def evaluate_pipeline(request: Request) -> JSONResponse:
    """
    Run the built-in ground-truth benchmark and return precision/recall/F1/accuracy.

    Optional JSON body:
      {"max_claims": N}              — evaluate on first N benchmark items
      {"adversarial": true}          — include adversarial benchmark (44 claims total)
      {"max_claims": N, "adversarial": true}
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    max_claims = body.get("max_claims", None)
    if max_claims is not None:
        try:
            max_claims = int(max_claims)
        except (ValueError, TypeError):
            max_claims = None
    adversarial = bool(body.get("adversarial", False))

    from .evaluation import evaluate_accuracy  # noqa: PLC0415
    result = await evaluate_accuracy(_pipeline_(), max_claims=max_claims, adversarial=adversarial)
    return JSONResponse({
        "benchmark": "adversarial" if adversarial else "standard",
        "total_claims": result.total,
        "precision": round(result.precision, 4),
        "recall": round(result.recall, 4),
        "f1": round(result.f1, 4),
        "accuracy": round(result.accuracy, 4),
        "true_positives": result.true_positives,
        "false_positives": result.false_positives,
        "true_negatives": result.true_negatives,
        "false_negatives": result.false_negatives,
        "details": result.details,
    })


@app.post("/evaluate/llm", dependencies=[Depends(verify_api_key)])
async def evaluate_llm_pipeline(request: Request) -> JSONResponse:
    """
    Empirical F1 — sends prompts that LLMs hallucinate on to the configured
    provider, then verifies actual LLM responses through the pipeline.
    Returns F1/precision/recall on real (not synthetic) LLM outputs.

    Optional JSON body: {"max_prompts": N}
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    max_prompts = body.get("max_prompts", None)
    if max_prompts is not None:
        try:
            max_prompts = int(max_prompts)
        except (ValueError, TypeError):
            max_prompts = None

    from .evaluation import evaluate_llm_empirical  # noqa: PLC0415
    result = await evaluate_llm_empirical(_pipeline_(), max_prompts=max_prompts)
    return JSONResponse({
        "benchmark": "empirical_llm",
        "llm_provider": result.llm_provider,
        "model": result.model,
        "total_prompts": result.total,
        "precision": round(result.precision, 4),
        "recall": round(result.recall, 4),
        "f1": round(result.f1, 4),
        "accuracy": round(result.accuracy, 4),
        "true_positives": result.true_positives,
        "false_positives": result.false_positives,
        "true_negatives": result.true_negatives,
        "false_negatives": result.false_negatives,
        "sample_outputs": result.sample_outputs,
    })


# ---------------------------------------------------------------------------
# Playground / direct verification endpoint
# ---------------------------------------------------------------------------

@app.post("/verify", dependencies=[Depends(verify_api_key)])
async def verify_text(request: Request) -> JSONResponse:
    """Verify arbitrary text through the full hallucination detection pipeline."""
    await _check_rate_limit(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    text = body.get("text", "")
    model = body.get("model", "playground")
    if not text.strip():
        raise HTTPException(400, "text field is required and must not be empty")
    _validate_text_length(text)
    audit = await _pipeline_().process(text, model=model)
    stub = {"id": audit.request_id, "content": [{"type": "text", "text": text}], "model": model}
    result = _inject_audit(stub, audit)
    payload = result["hallucination_audit"]
    payload["annotated_text"] = audit.annotated_text
    payload["original_text"] = audit.original_text
    payload["corrected_text"] = audit.corrected_text
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# SSE streaming verify endpoint
# ---------------------------------------------------------------------------

@app.post("/verify/stream", dependencies=[Depends(verify_api_key)])
async def verify_stream(request: Request) -> StreamingResponse:
    """
    Same as /verify but streams SSE progress events while the pipeline runs.
    Events: {stage, message} during processing; {stage:'done', result:{...}} on completion.
    """
    await _check_rate_limit(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    text = body.get("text", "")
    model = body.get("model", "playground")
    if not text.strip():
        raise HTTPException(400, "text field is required")
    _validate_text_length(text)

    queue: asyncio.Queue = asyncio.Queue()

    done_emitted = False

    async def _progress(stage: str, data: dict) -> None:
        nonlocal done_emitted
        if stage == "done":
            # Pipeline emits "done" immediately after decisions (before correction).
            # Forward it as the SSE done event so the client sees results ~20 s faster.
            done_emitted = True
            await queue.put({"stage": "done", "result": data.get("result", {})})
        elif stage == "corrected":
            # Self-correction finished — send corrected text as an incremental event.
            await queue.put({"stage": "corrected", "corrected_text": data.get("corrected_text")})
        else:
            await queue.put({"stage": stage, **{k: v for k, v in data.items() if k != "result"}})

    async def _run() -> None:
        try:
            audit = await _pipeline_().process(text, model=model, progress_cb=_progress)
            if not done_emitted:
                # Fallback: pipeline errored before emitting "done"
                stub = {"id": audit.request_id, "content": [{"type": "text", "text": text}], "model": model}
                flat = _inject_audit(stub, audit)
                payload = flat["hallucination_audit"]
                payload["annotated_text"] = audit.annotated_text
                payload["original_text"] = audit.original_text
                payload["corrected_text"] = audit.corrected_text
                await queue.put({"stage": "done", "result": payload})
        except Exception as exc:
            await queue.put({"stage": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    asyncio.create_task(_run())

    async def _event_gen() -> AsyncGenerator[str, None]:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=600.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Pipeline timed out after 10 min'})}\n\n"
                return
            if item is None:
                return
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Sentence-level streaming verification
# Verifies each complete sentence independently as it is identified, emitting
# a "sentence_verified" SSE event per sentence so clients see partial results
# without waiting for the full response to be processed.
# ---------------------------------------------------------------------------

@app.post("/verify/stream/sentences", dependencies=[Depends(verify_api_key)])
async def verify_stream_sentences(request: Request) -> StreamingResponse:
    """
    Sentence-level streaming: splits input text into sentences, then verifies
    each sentence independently and streams a 'sentence_verified' SSE event
    for each one as it completes.  Final 'done' event carries the full audit.

    This reduces first-result latency — clients see the first verdict in
    ~sentence_latency ms rather than waiting for all sentences.
    """
    await _check_rate_limit(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    text = body.get("text", "")
    model = body.get("model", "playground")
    if not text.strip():
        raise HTTPException(400, "text field is required")
    _validate_text_length(text)

    queue: asyncio.Queue = asyncio.Queue()

    async def _run_sentence_stream() -> None:
        try:
            import re
            # Split into sentences using spaCy if available, else regex
            try:
                import spacy
                s = get_settings()
                nlp = spacy.load(s.spacy_language_model, disable=["ner", "parser", "tagger"])
                nlp.enable_pipe("senter")
                doc = nlp(text[:100_000])
                sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
            except Exception:
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

            if not sentences:
                sentences = [text]

            all_decisions = []
            all_meta = []

            for i, sentence in enumerate(sentences):
                await queue.put({
                    "stage": "sentence_start",
                    "sentence_index": i,
                    "total_sentences": len(sentences),
                    "sentence": sentence[:200],
                })
                try:
                    audit = await _pipeline_().process(sentence, model=model)
                    sentence_result = {
                        "stage": "sentence_verified",
                        "sentence_index": i,
                        "total_sentences": len(sentences),
                        "sentence": sentence[:200],
                        "claims": [
                            {
                                "text": d.verified_claim.claim.text,
                                "status": d.verified_claim.status.value,
                                "confidence": d.verified_claim.confidence,
                                "action": d.action.value,
                                "annotation": d.annotation,
                            }
                            for d in audit.claims
                        ],
                        "overall_confidence": audit.overall_confidence,
                        "response_blocked": audit.response_blocked,
                    }
                    all_decisions.extend(audit.claims)
                    all_meta.extend(audit.retrieval_metadata)
                    await queue.put(sentence_result)
                except Exception as exc:
                    await queue.put({
                        "stage": "sentence_error",
                        "sentence_index": i,
                        "sentence": sentence[:200],
                        "message": str(exc),
                    })

            # Final done event — aggregate stats
            total = len(all_decisions)
            flagged = sum(1 for d in all_decisions if d.action.value == "flag")
            blocked = sum(1 for d in all_decisions if d.action.value == "block")
            avg_conf = round(sum(d.verified_claim.confidence for d in all_decisions) / total, 3) if total else 1.0
            await queue.put({
                "stage": "done",
                "total_sentences": len(sentences),
                "total_claims": total,
                "flagged_count": flagged,
                "blocked_count": blocked,
                "overall_confidence": avg_conf,
                "response_blocked": blocked > 0,
            })
        except Exception as exc:
            await queue.put({"stage": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    asyncio.create_task(_run_sentence_stream())

    async def _event_gen() -> AsyncGenerator[str, None]:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=600.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Timed out'})}\n\n"
                return
            if item is None:
                return
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# KB management endpoints (for frontend)
# ---------------------------------------------------------------------------

_WEB_ONLY_MSG = (
    "Running in web-only mode — all evidence is fetched live from the internet "
    "(Tavily + DuckDuckGo). Local knowledge base ingestion is disabled."
)


@app.post("/kb/ingest", dependencies=[Depends(verify_admin_key)])
async def kb_ingest(request: Request) -> JSONResponse:
    return JSONResponse({"status": "web-only", "message": _WEB_ONLY_MSG}, status_code=200)


@app.post("/kb/ingest/pdf", dependencies=[Depends(verify_admin_key)])
async def kb_ingest_pdf(request: Request) -> JSONResponse:
    return JSONResponse({"status": "web-only", "message": _WEB_ONLY_MSG}, status_code=200)


@app.get("/kb/search/wikipedia")
async def kb_search_wikipedia(q: str = "", language: str = "en", n: int = 8) -> JSONResponse:
    """Search Wikipedia and return matching article titles (live query — no ingestion)."""
    if not q.strip():
        raise HTTPException(400, "q (query) parameter is required")
    from .wikipedia_ingest import search_wikipedia  # noqa: PLC0415
    results = await asyncio.to_thread(search_wikipedia, q, n_results=min(n, 20), language=language)
    return JSONResponse({"results": results, "query": q})


@app.get("/kb/wikipedia/info")
async def kb_wikipedia_info(topic: str = "", language: str = "en") -> JSONResponse:
    """Return metadata about a Wikipedia page (live query — no ingestion)."""
    if not topic.strip():
        raise HTTPException(400, "topic parameter is required")
    from .wikipedia_ingest import get_page_info  # noqa: PLC0415
    info = await asyncio.to_thread(get_page_info, topic, language=language)
    if info is None:
        raise HTTPException(404, f"Wikipedia page not found: '{topic}'")
    return JSONResponse(info)


@app.post("/kb/ingest/wikipedia", dependencies=[Depends(verify_admin_key)])
async def kb_ingest_wikipedia(request: Request) -> JSONResponse:
    return JSONResponse({"status": "web-only", "message": _WEB_ONLY_MSG}, status_code=200)


@app.post("/audit/feedback")
async def submit_feedback(request: Request) -> JSONResponse:
    """Record user feedback (correct / incorrect) for a specific claim verification."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    claim_id = body.get("claim_id", "").strip()
    is_correct = body.get("is_correct")
    comment = body.get("comment", "")[:500]
    if not claim_id:
        raise HTTPException(400, "claim_id is required")
    if is_correct is None:
        raise HTTPException(400, "is_correct (boolean) is required")
    feedback_entry = {
        "type": "feedback",
        "claim_id": claim_id,
        "is_correct": bool(is_correct),
        "comment": comment,
        "timestamp": time.time(),
    }
    try:
        with open(settings.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry) + "\n")
        logger.info("Feedback logged: claim_id=%s is_correct=%s", claim_id, is_correct)
    except Exception as exc:
        logger.warning("Failed to write feedback: %s", exc)
    return JSONResponse({"status": "ok", "claim_id": claim_id, "is_correct": bool(is_correct)})


@app.delete("/kb/documents/{doc_id}", dependencies=[Depends(verify_admin_key)])
async def kb_delete_document(doc_id: str) -> JSONResponse:
    """Delete all chunks for a given document from the knowledge base."""
    kb = _pipeline_().knowledge_base
    deleted = kb.delete_document(doc_id)
    if deleted:
        await _pipeline_().invalidate_cache()
    return JSONResponse({"deleted_chunks": deleted, "doc_id": doc_id})


# ---------------------------------------------------------------------------
# SPA catch-all — serve index.html for all non-API routes
# ---------------------------------------------------------------------------

@app.get("/")
async def spa_root() -> FileResponse:
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "ok", "message": "Hallucination Detection API running"})


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_catchall(full_path: str) -> Response:
    # API and known paths pass through; everything else → SPA
    if full_path.startswith(("v1/", "health", "verify", "audit", "kb/", "cache/", "status/")):
        raise HTTPException(404)
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(404)


# ---------------------------------------------------------------------------
# Anthropic /v1/messages proxy
# ---------------------------------------------------------------------------

@app.post("/v1/messages", dependencies=[Depends(verify_api_key)])
async def proxy_messages(request: Request) -> Response:
    body = await request.body()
    try:
        req_data: Dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc

    was_streaming = bool(req_data.pop("stream", False))
    req_data_no_stream = {**req_data, "stream": False}

    if settings.llm_provider == "ollama":
        # Anthropic format → OpenAI format → Ollama → back to Anthropic
        oai_req = _anthropic_to_oai_request(req_data_no_stream)
        upstream_resp = await _call_upstream(
            f"{settings.ollama_base_url}/chat/completions",
            oai_req,
            {"Content-Type": "application/json", "Authorization": f"Bearer {settings.ollama_api_key}"},
        )
        if upstream_resp.status_code != 200:
            return Response(content=upstream_resp.content, status_code=upstream_resp.status_code,
                            media_type="application/json")
        try:
            oai_resp = upstream_resp.json()
        except Exception:
            return Response(content=upstream_resp.content, status_code=200, media_type="application/json")
        resp_data = _oai_response_to_anthropic(oai_resp, req_data_no_stream)
    elif settings.llm_provider == "nvidia_nim":
        # Anthropic format → OpenAI format → NVIDIA NIM → back to Anthropic
        oai_req = _anthropic_to_oai_request(req_data_no_stream)
        upstream_resp = await _call_upstream(
            f"{settings.nvidia_nim_base_url}/chat/completions",
            oai_req,
            {"Content-Type": "application/json", "Authorization": f"Bearer {settings.nvidia_nim_api_key}"},
        )
        if upstream_resp.status_code != 200:
            return Response(content=upstream_resp.content, status_code=upstream_resp.status_code,
                            media_type="application/json")
        try:
            oai_resp = upstream_resp.json()
        except Exception:
            return Response(content=upstream_resp.content, status_code=200, media_type="application/json")
        resp_data = _oai_response_to_anthropic(oai_resp, req_data_no_stream)
    else:
        # Anthropic provider: pass through directly
        api_key = _resolve_api_key(request)
        upstream_resp = await _call_upstream(
            f"{settings.anthropic_api_base}/v1/messages",
            req_data_no_stream,
            _anthropic_headers(request, api_key),
        )
        if upstream_resp.status_code != 200:
            return Response(content=upstream_resp.content, status_code=upstream_resp.status_code,
                            media_type="application/json")
        try:
            resp_data = upstream_resp.json()
        except Exception:
            return Response(content=upstream_resp.content, status_code=200, media_type="application/json")
    text_content = _extract_text(resp_data)
    if not text_content:
        return JSONResponse(resp_data)

    audit = await _pipeline_().process(
        text_content,
        model=resp_data.get("model", ""),
        request_id=resp_data.get("id"),
    )
    resp_data = _inject_audit(resp_data, audit)

    if was_streaming:
        return StreamingResponse(
            _restream_as_sse(resp_data),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return JSONResponse(resp_data)


async def _restream_as_sse(resp_data: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """Re-emit a verified non-streaming response as Anthropic SSE chunks."""
    text = _extract_text(resp_data)
    audit_payload = resp_data.get("hallucination_audit", {})

    # message_start
    yield _sse({"type": "message_start", "message": {
        "id": resp_data.get("id", ""),
        "type": "message",
        "role": "assistant",
        "model": resp_data.get("model", ""),
        "content": [],
        "stop_reason": None,
        "usage": resp_data.get("usage", {}),
    }})

    yield _sse({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})

    # Stream in ~200-char chunks for responsiveness
    chunk_size = 200
    for i in range(0, max(len(text), 1), chunk_size):
        yield _sse({"type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": text[i:i + chunk_size]}})

    yield _sse({"type": "content_block_stop", "index": 0})

    # Inject hallucination audit as a custom event before message_stop
    yield _sse({"type": "hallucination_audit", **audit_payload})

    yield _sse({"type": "message_delta",
                "delta": {"stop_reason": resp_data.get("stop_reason", "end_turn"), "stop_sequence": None},
                "usage": {"output_tokens": resp_data.get("usage", {}).get("output_tokens", 0)}})
    yield _sse({"type": "message_stop"})
    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# OpenAI /v1/chat/completions compatibility
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def proxy_openai(request: Request) -> Response:
    """
    Accept OpenAI ChatCompletion format, convert to Anthropic, verify,
    convert response back to OpenAI format.
    """
    body = await request.body()
    try:
        oai_req: Dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc

    api_key = _resolve_api_key(request)
    was_streaming = bool(oai_req.get("stream", False))

    # Convert OpenAI → Anthropic
    anthropic_req = _oai_to_anthropic(oai_req)
    anthropic_req["stream"] = False

    upstream_resp = await _call_upstream(
        f"{settings.anthropic_api_base}/v1/messages",
        anthropic_req,
        _anthropic_headers(request, api_key),
        stream=False,
    )
    if upstream_resp.status_code != 200:
        # Re-wrap upstream error in OpenAI error format
        return JSONResponse(
            {"error": {"message": "Upstream error", "code": upstream_resp.status_code}},
            status_code=upstream_resp.status_code,
        )

    try:
        anthropic_resp: Dict[str, Any] = upstream_resp.json()
    except Exception:
        return Response(content=upstream_resp.content, status_code=200, media_type="application/json")

    text_content = _extract_text(anthropic_resp)
    if text_content:
        audit = await _pipeline_().process(
            text_content,
            model=anthropic_resp.get("model", oai_req.get("model", "")),
            request_id=anthropic_resp.get("id"),
        )
        anthropic_resp = _inject_audit(anthropic_resp, audit)

    oai_resp = _anthropic_to_oai(anthropic_resp, oai_req.get("model", ""))

    if was_streaming:
        return StreamingResponse(
            _restream_oai_sse(oai_resp),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    return JSONResponse(oai_resp)


async def _restream_oai_sse(oai_resp: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """Re-stream an OpenAI-format response as SSE chunks."""
    text = oai_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    chunk_id = oai_resp.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}")
    model = oai_resp.get("model", "")

    chunk_size = 200
    for i in range(0, max(len(text), 1), chunk_size):
        yield _sse({
            "id": chunk_id, "object": "chat.completion.chunk", "model": model,
            "choices": [{"index": 0, "delta": {"content": text[i:i + chunk_size]},
                         "finish_reason": None}],
        })

    yield _sse({
        "id": chunk_id, "object": "chat.completion.chunk", "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "hallucination_audit": oai_resp.get("hallucination_audit"),
    })
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _oai_to_anthropic(oai: Dict[str, Any]) -> Dict[str, Any]:
    messages = oai.get("messages", [])
    system_parts: List[str] = []
    filtered: List[Dict] = []

    for m in messages:
        if m.get("role") == "system":
            content = m.get("content", "")
            if isinstance(content, list):
                system_parts.extend(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
            else:
                system_parts.append(str(content))
        else:
            filtered.append(m)

    req: Dict[str, Any] = {
        "model": oai.get("model", settings.verifier_model),
        "messages": filtered,
        "max_tokens": oai.get("max_tokens") or oai.get("max_completion_tokens") or 4096,
    }
    if system_parts:
        req["system"] = "\n\n".join(system_parts)
    if oai.get("temperature") is not None:
        req["temperature"] = oai["temperature"]
    if oai.get("stop"):
        req["stop_sequences"] = (
            oai["stop"] if isinstance(oai["stop"], list) else [oai["stop"]]
        )
    return req


def _anthropic_to_oai(ant: Dict[str, Any], model: str) -> Dict[str, Any]:
    text = _extract_text(ant)
    finish = "stop"
    sr = ant.get("stop_reason", "end_turn")
    if sr == "max_tokens":
        finish = "length"
    elif sr == "tool_use":
        finish = "tool_calls"

    usage = ant.get("usage", {})
    resp = {
        "id": ant.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or ant.get("model", ""),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": finish,
        }],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }
    if "hallucination_audit" in ant:
        resp["hallucination_audit"] = ant["hallucination_audit"]
    return resp


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_api_key(request: Request) -> str:
    key = (
        request.headers.get("x-api-key")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        or settings.anthropic_api_key
    )
    if not key:
        raise HTTPException(401, "No Anthropic API key provided.")
    return key


def _anthropic_headers(request: Request, api_key: str) -> Dict[str, str]:
    h = {
        "x-api-key": api_key,
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
        "content-type": "application/json",
    }
    if beta := request.headers.get("anthropic-beta"):
        h["anthropic-beta"] = beta
    return h


async def _call_upstream(
    url: str,
    data: Dict[str, Any],
    headers: Dict[str, str],
    stream: bool = False,
) -> httpx.Response:
    client = _http_client
    if client is None:
        raise HTTPException(503, "HTTP client not initialized")
    try:
        return await client.post(url, content=json.dumps(data).encode(), headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Upstream API timeout") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Upstream API error: {exc}") from exc


def _extract_text(resp: Dict[str, Any]) -> str:
    return "\n".join(
        b.get("text", "")
        for b in resp.get("content", [])
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _inject_audit(resp: Dict[str, Any], audit: Any) -> Dict[str, Any]:
    content = resp.get("content", [])
    if audit.annotated_text and content:
        new_content, replaced = [], False
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and not replaced:
                new_content.append({**block, "text": audit.annotated_text})
                replaced = True
            else:
                new_content.append(block)
        resp["content"] = new_content

    resp["hallucination_audit"] = {
        "request_id": audit.request_id,
        "timestamp": audit.timestamp,
        "total_claims": audit.total_claims,
        "verified_count": audit.verified_count,
        "partially_supported_count": audit.partially_supported_count,
        "unverifiable_count": audit.unverifiable_count,
        "contradicted_count": audit.contradicted_count,
        "flagged_count": audit.flagged_count,
        "blocked_count": audit.blocked_count,
        "cache_hits": audit.cache_hits,
        "overall_confidence": audit.overall_confidence,
        "response_blocked": audit.response_blocked,
        "block_reason": audit.block_reason,
        "processing_time_ms": audit.processing_time_ms,
        "claims": [
            {
                "id": d.verified_claim.claim.id,
                "text": d.verified_claim.claim.text,
                "normalized": d.verified_claim.claim.normalized,
                "type": d.verified_claim.claim.claim_type.value,
                "stakes": d.verified_claim.claim.stakes.value,
                "category": d.verified_claim.claim.category,
                "status": d.verified_claim.status.value,
                "confidence": d.verified_claim.confidence,
                "action": d.action.value,
                "annotation": d.annotation,
                "reasoning": d.verified_claim.verification_reasoning,
                "key_evidence": (d.verified_claim.key_evidence or "")[:300],
                "sources": [s.source for s in d.verified_claim.supporting_docs[:3]],
                "rerank_scores": [
                    s.rerank_score for s in d.verified_claim.supporting_docs[:3]
                    if s.rerank_score is not None
                ],
            }
            for d in audit.claims
        ],
        "retrieval_metadata": [
            {
                "claim_id": m.claim_id,
                "query_variants": m.query_variants,
                "total_retrieved": m.total_retrieved,
                "total_after_rerank": m.total_after_rerank,
                "cache_hit": m.cache_hit,
                "ensemble_used": m.ensemble_used,
            }
            for m in audit.retrieval_metadata
        ],
    }
    return resp


# ---------------------------------------------------------------------------
# Ollama ↔ Anthropic format conversion
# ---------------------------------------------------------------------------

def _anthropic_to_oai_request(ant: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an Anthropic /v1/messages request to OpenAI /v1/chat/completions format."""
    messages: List[Dict] = []

    system = ant.get("system")
    if isinstance(system, str) and system:
        messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        text = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
        if text:
            messages.append({"role": "system", "content": text})

    for m in ant.get("messages", []):
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        else:
            text = str(content)
        messages.append({"role": role, "content": text})

    req: Dict[str, Any] = {
        "model": ant.get("model", settings.verifier_model),
        "messages": messages,
        "max_tokens": ant.get("max_tokens", 4096),
        "stream": False,
    }
    if ant.get("temperature") is not None:
        req["temperature"] = ant["temperature"]
    return req


def _oai_response_to_anthropic(oai: Dict[str, Any], original_req: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an OpenAI chat completion response back to Anthropic /v1/messages format."""
    text = oai.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = oai.get("usage", {})
    finish = oai.get("choices", [{}])[0].get("finish_reason", "stop")

    stop_reason = "end_turn"
    if finish == "length":
        stop_reason = "max_tokens"

    return {
        "id": oai.get("id", f"msg_{uuid.uuid4().hex[:16]}"),
        "type": "message",
        "role": "assistant",
        "model": oai.get("model", original_req.get("model", "")),
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
