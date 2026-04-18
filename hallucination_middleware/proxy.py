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
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .audit_trail import AuditTrail
from .config import get_settings
from .pipeline import HallucinationDetectionPipeline

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# App + lifecycle
# ---------------------------------------------------------------------------

_pipeline: Optional[HallucinationDetectionPipeline] = None
_audit: Optional[AuditTrail] = None


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


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _pipeline, _audit
    logger.info("Initialising hallucination detection pipeline …")
    _pipeline = HallucinationDetectionPipeline()
    _audit = AuditTrail()
    logger.info(
        "Proxy ready on %s:%s  →  %s",
        settings.proxy_host, settings.proxy_port, settings.anthropic_api_base,
    )
    # Pre-warm Ollama model in background so first user request is faster
    asyncio.create_task(_warmup_ollama())
    yield
    logger.info("Proxy shutting down")


app = FastAPI(
    title="Hallucination Detection Proxy v2",
    description="Advanced real-time LLM hallucination detection middleware.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve React SPA from frontend/dist if it exists
_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")


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

@app.get("/health")
async def health() -> JSONResponse:
    kb = _pipeline_().knowledge_base
    return JSONResponse({
        "status": "ok",
        "knowledge_base": kb.stats(),
        "cache": _pipeline_().cache_stats(),
        "audit": _audit_().get_stats(),
    })


@app.get("/audit/recent")
async def recent_audit(n: int = 10) -> JSONResponse:
    return JSONResponse(_audit_().read_recent(n))


@app.get("/audit/stats")
async def audit_stats() -> JSONResponse:
    return JSONResponse(_audit_().get_stats())


@app.get("/kb/stats")
async def kb_stats() -> JSONResponse:
    return JSONResponse(_pipeline_().knowledge_base.stats())


@app.get("/kb/documents")
async def kb_documents() -> JSONResponse:
    return JSONResponse(_pipeline_().knowledge_base.list_documents())


@app.get("/cache/stats")
async def cache_stats() -> JSONResponse:
    return JSONResponse(_pipeline_().cache_stats())


@app.post("/cache/clear")
async def cache_clear() -> JSONResponse:
    _pipeline_().invalidate_cache()
    return JSONResponse({"status": "ok", "message": "Cache cleared"})


# ---------------------------------------------------------------------------
# Playground / direct verification endpoint
# ---------------------------------------------------------------------------

@app.post("/verify")
async def verify_text(request: Request) -> JSONResponse:
    """Verify arbitrary text through the full hallucination detection pipeline."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    text = body.get("text", "")
    model = body.get("model", "playground")
    if not text.strip():
        raise HTTPException(400, "text field is required and must not be empty")
    audit = await _pipeline_().process(text, model=model)
    _audit_().log(audit)
    stub = {"id": audit.request_id, "content": [{"type": "text", "text": text}], "model": model}
    result = _inject_audit(stub, audit)
    payload = result["hallucination_audit"]
    payload["annotated_text"] = audit.annotated_text
    payload["original_text"] = audit.original_text
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# KB management endpoints (for frontend)
# ---------------------------------------------------------------------------

@app.post("/kb/ingest")
async def kb_ingest(request: Request) -> JSONResponse:
    """Ingest text or fetch a URL into the knowledge base."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc

    url = body.get("url", "").strip()
    text = body.get("text", "").strip()
    source = body.get("source", "")
    kb = _pipeline_().knowledge_base

    if url:
        source = source or url
        try:
            chunks = await kb.ingest_url(url, source=source)
        except Exception as exc:
            raise HTTPException(500, f"URL ingestion failed: {exc}") from exc
        return JSONResponse({"chunks_added": chunks, "source": source, "type": "url"})

    if text:
        source = source or "manual-upload"
        chunks = kb.ingest_text(text, source=source)
        return JSONResponse({"chunks_added": chunks, "source": source, "type": "text"})

    raise HTTPException(400, "Provide either 'text' or 'url' in the request body")


@app.post("/kb/ingest/wikipedia")
async def kb_ingest_wikipedia(request: Request) -> JSONResponse:
    """Ingest a Wikipedia article into the knowledge base by topic title."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc
    topic = body.get("topic", "").strip()
    language = body.get("language", "en").strip() or "en"
    if not topic:
        raise HTTPException(400, "topic is required")
    try:
        from .wikipedia_ingest import ingest_from_wikipedia  # noqa: PLC0415
        chunks = await asyncio.to_thread(ingest_from_wikipedia, topic, language=language)
    except Exception as exc:
        raise HTTPException(500, f"Wikipedia ingestion failed: {exc}") from exc
    return JSONResponse({"chunks_added": chunks, "topic": topic, "language": language})


@app.delete("/kb/documents/{doc_id}")
async def kb_delete_document(doc_id: str) -> JSONResponse:
    """Delete all chunks for a given document from the knowledge base."""
    kb = _pipeline_().knowledge_base
    deleted = kb.delete_document(doc_id)
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
    if full_path.startswith(("v1/", "health", "verify", "audit/", "kb/", "cache/")):
        raise HTTPException(404)
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(404)


# ---------------------------------------------------------------------------
# Anthropic /v1/messages proxy
# ---------------------------------------------------------------------------

@app.post("/v1/messages")
async def proxy_messages(request: Request) -> Response:
    body = await request.body()
    try:
        req_data: Dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc

    was_streaming = bool(req_data.pop("stream", False))
    req_data_no_stream = {**req_data, "stream": False}

    if settings.llm_provider == "ollama":
        # Convert Anthropic format → OpenAI format → send to Ollama → convert back
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
    else:
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

@app.post("/v1/chat/completions")
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
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
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
                "type": d.verified_claim.claim.claim_type.value,
                "stakes": d.verified_claim.claim.stakes.value,
                "status": d.verified_claim.status.value,
                "confidence": d.verified_claim.confidence,
                "action": d.action.value,
                "annotation": d.annotation,
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
