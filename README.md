# Hallucination Detection Middleware

A real-time hallucination detection proxy for LLM responses. It intercepts LLM output, extracts factual claims, verifies them against a ChromaDB knowledge base using RAG, and returns a structured audit with BLOCK / FLAG / ANNOTATE / PASS decisions.

---

## Architecture

```
Browser (React SPA)
      │
      ▼
FastAPI Proxy :8080
      │
      ├── Claim Extractor ──► Ollama (llama3.2)
      │                         extracts factual claims
      │
      ├── Verifier ─────────► ChromaDB + BM25 (hybrid RAG)
      │                         retrieves evidence chunks
      │                    ──► Ollama (llama3.2)
      │                         verifies each claim
      │
      ├── Decision Engine ──► BLOCK / FLAG / ANNOTATE / PASS
      │
      └── Audit Trail ──────► audit_trail.jsonl
```

**Components:**
- **FastAPI proxy** — 11 REST endpoints, serves React SPA from `/`
- **ChromaDB** — vector store for authoritative knowledge base
- **BM25** — keyword search (hybrid with vector search)
- **Ollama** — free local LLM inference (llama3.2 by default)
- **React SPA** — Playground, Dashboard, Knowledge Base, Audit Log, Settings

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) (free, runs locally)
- Node.js 18+ (only needed to rebuild the frontend)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install and start Ollama

```bash
# Install from https://ollama.ai, then:
ollama serve          # start the Ollama server
ollama pull llama3.2  # download the model (~2 GB, one-time)
```

### 3. Configure (optional)

```bash
cp .env.example .env
# Edit .env to change models, thresholds, or ports
```

### 4. Start the backend

```bash
python run_proxy.py
```

The server starts on **http://localhost:8080**. On first startup it warm-warms Ollama in the background (model loads in ~60s).

### 5. Open the UI

Navigate to **http://localhost:8080** in your browser.

---

## Usage

### Playground

Paste any LLM response into the Playground and click **Detect Hallucinations**. The system will:

1. Extract factual claims from the text
2. Search the knowledge base for evidence
3. Verify each claim and assign a confidence score
4. Decide: **PASS** (verified) / **ANNOTATE** (low confidence) / **FLAG** (suspicious) / **BLOCK** (dangerous)

### Knowledge Base

Add authoritative documents via:
- **Plain text** — paste text with a source name
- **URL** — fetch and ingest a webpage
- **Wikipedia** — search and ingest any Wikipedia article

Without knowledge base content, all claims will be marked `UNVERIFIABLE`.

### Audit Log

All verification requests are logged. View history, filter by action type, and export as JSON or CSV.

---

## Configuration

Key settings in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` (free/local) or `anthropic` (paid) |
| `EXTRACTOR_MODEL` | `llama3.2` | Ollama model for claim extraction |
| `VERIFIER_MODEL` | `llama3.2` | Ollama model for verification |
| `BLOCK_THRESHOLD` | `0.25` | Confidence below this → BLOCK |
| `FLAG_THRESHOLD` | `0.60` | Confidence below this → FLAG |
| `MAX_CLAIMS_PER_RESPONSE` | `8` | Cap on claims extracted per request |
| `KB_TOP_K` | `3` | Documents retrieved per query |
| `MULTI_QUERY_COUNT` | `2` | Query variants per claim |
| `RERANKER_ENABLED` | `false` | Cross-encoder reranking (accurate but slow) |
| `CACHE_ENABLED` | `true` | Cache verified claims (speeds up repeated queries) |

---

## Performance Guide

### Why is the first request slow?

Each verification request makes **multiple LLM calls through Ollama**:

| Step | LLM calls |
|------|-----------|
| Claim extraction | 1 |
| Query expansion (per claim) | 1 × N claims |
| Batch verification | 1 |
| **Total (5 claims)** | **~7 calls** |

At 10–30s per Ollama call, that's **70–210 seconds**. On first run, add **60–180s** for model loading.

**Second requests are much faster** — the claim cache (`CACHE_ENABLED=true`) means verified claims are reused instantly.

### Speed-up options

1. **Reduce claims extracted** — set `MAX_CLAIMS_PER_RESPONSE=5`
2. **Disable query expansion** — set `MULTI_QUERY_ENABLED=false`
3. **Use Anthropic API** — set `LLM_PROVIDER=anthropic` (requires API key, ~10× faster)
4. **Use a smaller/faster model** — e.g., `EXTRACTOR_MODEL=llama3.2:1b`
5. **Pre-warm on startup** — the proxy automatically sends a warm-up request to Ollama on startup

---

## API Reference

All endpoints are available at `http://localhost:8080`.

Interactive docs: **http://localhost:8080/docs**

### Verification

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/verify` | Verify text for hallucinations |

```bash
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{"text": "Einstein was born in Berlin in 1879."}'
```

Response:
```json
{
  "request_id": "...",
  "total_claims": 2,
  "verified_count": 1,
  "flagged_count": 1,
  "blocked_count": 0,
  "overall_confidence": 0.72,
  "response_blocked": false,
  "processing_time_ms": 4230,
  "claims": [
    {
      "id": "...",
      "text": "Einstein was born in Berlin",
      "type": "geographic",
      "stakes": "medium",
      "status": "contradicted",
      "confidence": 0.45,
      "action": "flag",
      "annotation": "[FLAGGED: Einstein was born in Ulm, not Berlin]",
      "key_evidence": "Albert Einstein was born on 14 March 1879 in Ulm, Kingdom of Württemberg"
    }
  ]
}
```

### Knowledge Base

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/kb/stats` | Collection statistics |
| `GET` | `/kb/documents` | List all documents |
| `POST` | `/kb/ingest` | Ingest text or URL |
| `POST` | `/kb/ingest/wikipedia` | Ingest Wikipedia article |
| `DELETE` | `/kb/documents/{doc_id}` | Delete a document |

### Audit

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/audit/recent?n=50` | Recent audit entries |
| `GET` | `/audit/stats` | Aggregate statistics |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + stats |
| `GET` | `/cache/stats` | Cache hit rate |
| `POST` | `/cache/clear` | Clear verification cache |

---

## Troubleshooting

### "Request timed out"

1. Make sure Ollama is running: `ollama serve`
2. Make sure the model is downloaded: `ollama pull llama3.2`
3. Start the backend: `python run_proxy.py`
4. **First request takes 1–3 minutes** while Ollama loads the model — this is normal. Subsequent requests are faster.

### "Backend unreachable"

Make sure `run_proxy.py` is running and listening on port 8080:
```bash
python run_proxy.py
# Should print: Proxy ready on 0.0.0.0:8080
```

### "No claims detected"

The text may not contain verifiable factual statements. Try using one of the sample texts in the Playground.

### "All claims UNVERIFIABLE"

The knowledge base is empty. Add documents via the Knowledge Base page or Settings → Wikipedia Quick Ingest.

### Port 8080 already in use

Change the port in `.env`:
```ini
PROXY_PORT=8081
```

---

## Project Structure

```
hallucination_middleware/
├── proxy.py           FastAPI server, all API endpoints
├── pipeline.py        Main detection pipeline orchestrator
├── claim_extractor.py LLM-based claim extraction
├── verifier.py        Claim verification against KB
├── knowledge_base.py  ChromaDB + BM25 hybrid search
├── decision_engine.py BLOCK/FLAG/ANNOTATE/PASS logic
├── audit_trail.py     JSONL audit logging
├── cache.py           Two-level claim cache (memory + Redis)
├── reranker.py        Cross-encoder reranking (optional)
├── models.py          Pydantic data models
├── config.py          Settings from .env
├── wikipedia_ingest.py Wikipedia article ingestion
└── web_search.py      DuckDuckGo/Tavily web search

frontend/src/
├── App.jsx            Router + ToastProvider
├── api.js             All API calls with timeout
└── components/
    ├── Playground.jsx  Verification UI with claim table
    ├── Dashboard.jsx   Charts and statistics
    ├── KnowledgeBase.jsx Document management
    ├── AuditLog.jsx    Audit history with export
    ├── Settings.jsx    Config display + cache controls
    ├── Navbar.jsx      Navigation + live health status
    └── Toast.jsx       Global toast notifications

run_proxy.py           Entry point — starts uvicorn server
demo.py                Command-line demo / smoke test
requirements.txt       Python dependencies
.env.example           Configuration template
```

---

## Development

### Rebuild the frontend

```bash
cd frontend
npm install
npm run build
```

The built files go to `frontend/dist/` and are served automatically by the FastAPI proxy.

### Run demo (no browser needed)

```bash
python demo.py
```

Tests 4 sample texts and prints a claim table to the terminal.

### Run with auto-reload

```bash
python run_proxy.py --reload
```
