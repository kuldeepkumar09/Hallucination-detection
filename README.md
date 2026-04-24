# Hallucination Detection Middleware v3

A real-time hallucination detection proxy for LLM responses. It intercepts LLM output, extracts factual claims with domain classification (MEDICAL / LEGAL / FINANCIAL / GENERAL), verifies them against a ChromaDB knowledge base with live Web-RAG fallback, applies domain-specific blocking thresholds, self-corrects flagged responses, and optionally refines output through an MPC (Model Predictive Control) receding-horizon loop.

---

## Architecture

```
Browser (React SPA)
      │
      ▼
FastAPI Proxy :8080
      │
      ├── Claim Extractor ──► NVIDIA NIM / Ollama / Anthropic
      │                         extracts claims + assigns category
      │                         (MEDICAL | LEGAL | FINANCIAL | GENERAL)
      │
      ├── Verifier ─────────► ChromaDB + BM25 (hybrid RAG)
      │                         retrieves & re-ranks evidence chunks
      │                    ──► Web-RAG fallback (Tavily / DuckDuckGo)
      │                         triggered when KB score < 0.40
      │                    ──► LLM verifies each claim
      │
      ├── Decision Engine ──► Domain-specific thresholds
      │                         MEDICAL 0.95 | LEGAL 0.90
      │                         FINANCIAL 0.85 | GENERAL 0.40
      │                    ──► BLOCK / FLAG / ANNOTATE / PASS
      │
      ├── Self-Corrector ───► rewrites flagged/blocked text using evidence
      │
      ├── MPC Controller ───► receding-horizon refinement (optional)
      │                         N=3 candidates per sentence → KB-scored
      │
      └── Audit Trail ──────► audit_trail.jsonl
```

**Components:**
- **FastAPI proxy** — REST endpoints + OpenAI-compatible `/v1/chat/completions`, serves React SPA
- **ChromaDB** — vector store for authoritative knowledge base (748 Wikipedia chunks pre-loaded)
- **BM25** — keyword search (hybrid with vector search, configurable weight)
- **NVIDIA NIM** — fast free-tier cloud inference (`meta/llama-3.1-8b-instruct`, ~10× faster than Ollama)
- **Ollama** — free local LLM inference (`phi3:mini` by default)
- **Web-RAG** — automatic live web fallback (Tavily → DuckDuckGo) when KB relevance < 0.40
- **SelfCorrector** — rewrites BLOCK/FLAG claims using retrieved evidence before responding
- **MPC Controller** — receding-horizon loop: generates 3 candidate phrasings per sentence, picks most KB-supported
- **Semantic cache** — cosine-similarity cache to skip re-verifying near-identical claims
- **React SPA** — Playground (category badges, before/after diff), Dashboard (live counters), Knowledge Base, Audit Log, Settings

---

## Quick Start

### Prerequisites

- Python 3.10+
- One of: [NVIDIA NIM](https://build.nvidia.com) free account (recommended) or [Ollama](https://ollama.ai)
- Node.js 18+ (only needed to rebuild the frontend)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Choose your LLM provider

**Option A — NVIDIA NIM (recommended, ~10× faster, free tier):**
```bash
# 1. Create free account at https://build.nvidia.com
# 2. Generate API key → paste into .env
# In .env:
LLM_PROVIDER=nvidia_nim
NVIDIA_NIM_API_KEY=nvapi-your-key-here
EXTRACTOR_MODEL=meta/llama-3.1-8b-instruct
VERIFIER_MODEL=meta/llama-3.3-70b-instruct
```

**Option B — Ollama (free, local, no account needed):**
```bash
ollama serve            # start the Ollama server
ollama pull phi3:mini   # download model (~2 GB, one-time)
# .env already defaults to Ollama — no changes needed
```

**Option C — Anthropic Claude:**
```bash
# In .env:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
EXTRACTOR_MODEL=claude-haiku-4-5-20251001
VERIFIER_MODEL=claude-sonnet-4-6
```

### 3. Start the backend

```bash
python run_proxy.py
```

The server starts on **http://localhost:8080**.

### 4. Populate the knowledge base

```bash
# Pre-load 5 Wikipedia articles (Albert Einstein, Marie Curie, Penicillin, COVID-19 vaccine, Isaac Newton)
python ingest_wikipedia.py "Albert Einstein" "Marie Curie" "Penicillin" "COVID-19 vaccine" "Isaac Newton"
```

### 5. Open the UI

Navigate to **http://localhost:8080** in your browser.

---

## Usage

### Playground

Paste any LLM response into the Playground and click **Detect Hallucinations**. The system will:

1. Extract factual claims — each labelled **MEDICAL / LEGAL / FINANCIAL / GENERAL**
2. Search the knowledge base for evidence; fall back to live web search if KB score < 0.40
3. Verify each claim and assign a confidence score
4. Apply domain-specific thresholds: MEDICAL claims need 0.97+ to pass; GENERAL claims need 0.60+
5. Decide: **PASS** / **ANNOTATE** / **FLAG** / **BLOCK**
6. If `SELF_CORRECTION_ENABLED=true`, silently rewrite BLOCK/FLAG claims
7. Show **Before / After** side-by-side comparison in the UI

### Knowledge Base

Add authoritative documents via:
- **Plain text** — paste text with a source name
- **URL** — fetch and ingest a webpage
- **Wikipedia** — search and ingest any Wikipedia article
- **CLI** — `python ingest_docs.py ingest ./docs/` (supports `.txt`, `.pdf`)

Without knowledge base content, claims fall back to Web-RAG (live internet search).

### Audit Log

All verification requests are logged. View history, filter by action type, and export as JSON or CSV.

### Dashboard

Live metrics (auto-refresh every 10 s):
- **Blocked Claims** — total claims blocked across all requests
- **Flagged Claims** — total claims flagged
- **Corrected Responses** — responses where self-correction was applied

---

## Configuration

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `nvidia_nim` \| `anthropic` |
| `EXTRACTOR_MODEL` | `phi3:mini` | Model for claim extraction |
| `VERIFIER_MODEL` | `phi3:mini` | Model for verification |
| `NVIDIA_NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NIM endpoint |
| `NVIDIA_NIM_API_KEY` | `` | NIM API key (free at build.nvidia.com) |
| `ANTHROPIC_API_KEY` | `` | Anthropic key (only if LLM_PROVIDER=anthropic) |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama server URL |
| `BLOCK_THRESHOLD` | `0.50` | Global fallback block threshold |
| `FLAG_THRESHOLD` | `0.60` | Global fallback flag threshold |
| `DOMAIN_BLOCK_THRESHOLDS` | `MEDICAL:0.95, LEGAL:0.90, FINANCIAL:0.85, GENERAL:0.40` | Per-category block thresholds |
| `DOMAIN_FLAG_THRESHOLDS` | `MEDICAL:0.97, LEGAL:0.93, FINANCIAL:0.90, GENERAL:0.60` | Per-category flag thresholds |
| `MAX_CLAIMS_PER_RESPONSE` | `8` | Cap on claims extracted per request |
| `KB_TOP_K` | `3` | Documents retrieved per query |
| `KB_CHUNK_SIZE` | `512` | Token chunk size when ingesting |
| `KB_CHUNK_OVERLAP` | `64` | Token overlap between chunks |
| `BM25_ENABLED` | `true` | Hybrid BM25 + vector search |
| `BM25_WEIGHT` | `0.70` | BM25 share of hybrid score |
| `WEB_RAG_ENABLED` | `true` | Fall back to live web when KB score is low |
| `WEB_RAG_KB_THRESHOLD` | `0.40` | KB relevance below this triggers web search |
| `TAVILY_API_KEY` | `` | Tavily key for web search; DuckDuckGo used as fallback |
| `MULTI_QUERY_ENABLED` | `true` | Generate query variants per claim |
| `MULTI_QUERY_COUNT` | `2` | Number of query variants |
| `HYDE_ENABLED` | `false` | Generate a hypothetical doc before querying |
| `RERANKER_ENABLED` | `false` | Cross-encoder reranking (accurate but slow) |
| `RERANKER_CANDIDATE_COUNT` | `10` | Retrieve this many docs before reranking |
| `CACHE_ENABLED` | `true` | Cache verified claims |
| `CACHE_TTL_SECONDS` | `3600` | Cache TTL |
| `REDIS_URL` | `` | Redis URL for distributed cache; empty = in-memory |
| `SEMANTIC_CACHE_ENABLED` | `true` | Skip re-verification for near-identical claims |
| `SEMANTIC_CACHE_THRESHOLD` | `0.85` | Cosine similarity threshold for semantic cache |
| `ENSEMBLE_FOR_CRITICAL` | `false` | Run a second model on high-stakes claims |
| `ENSEMBLE_MODEL` | `phi3:mini` | Second model for ensemble verification |
| `SELF_CORRECTION_ENABLED` | `true` | Rewrite BLOCK/FLAG claims using evidence |
| `MPC_ENABLED` | `false` | Receding-horizon MPC refinement (expensive) |
| `MPC_CANDIDATES` | `3` | Candidate alternatives per sentence in MPC loop |
| `ANNOTATE_VERIFIED` | `true` | Append inline annotation tags to response |
| `MAX_WORKERS` | `4` | Concurrent pipeline executions |
| `REQUEST_TIMEOUT` | `480.0` | Per-request LLM timeout (seconds) |

---

## Domain-Specific Thresholds

Claims are automatically classified into one of four categories. Each category has its own block and flag confidence thresholds:

| Category | Block at | Flag at | Example claims |
|----------|----------|---------|----------------|
| `MEDICAL` | < 0.95 | < 0.97 | Drug dosages, diagnoses, treatment recommendations |
| `LEGAL` | < 0.90 | < 0.93 | Regulations, court rulings, fines, legal dates |
| `FINANCIAL` | < 0.85 | < 0.90 | GDP figures, market data, interest rates |
| `GENERAL` | < 0.40 | < 0.60 | History, science, geography, technology |

A medical claim like "Ibuprofen is safe in all pregnancy trimesters" will be **BLOCKED** unless the KB evidence confidence is ≥ 0.95 — far stricter than the 0.50 default.

---

## Web-RAG Fallback

When the knowledge base returns a top relevance score below `WEB_RAG_KB_THRESHOLD` (default 0.40), the verifier automatically queries the live internet:

1. **Tavily** (primary) — AI-optimized results, requires free API key
2. **DuckDuckGo** (fallback) — always free, no key required

Web results are merged with KB results and passed to the LLM verifier. Log output shows `[Web-RAG] KB top score X.XX < 0.40 — querying web`.

---

## MPC Controller (Optional)

When `MPC_ENABLED=true`, the pipeline adds a receding-horizon refinement step after self-correction:

1. Split text into sentences
2. For each sentence, generate **N=3 candidate alternative phrasings** via the LLM
3. Score each candidate by querying the KB — higher average relevance = lower cost
4. Select the lowest-cost (most factual) candidate
5. Append selected sentence to rolling context → repeat for the next sentence

This prevents hallucinations at the sentence level rather than correcting them after the fact. Enabled via `MPC_ENABLED=true` in `.env`. Off by default — adds ~3× LLM calls per sentence.

---

## Performance Guide

### LLM calls per request (5 claims, Ollama)

| Step | LLM calls |
|------|-----------|
| Claim extraction | 1 |
| Query expansion (per claim) | 1 × 5 = 5 |
| Batch verification | 1 |
| Self-correction (if triggered) | 1 |
| **Total** | **~8 calls** |

At 10–30 s per Ollama call → **80–240 seconds**. With NVIDIA NIM → **4–8 seconds**.

### Speed-up options

1. **Switch to NVIDIA NIM** — set `LLM_PROVIDER=nvidia_nim` (~10× faster, free tier)
2. **Switch to Anthropic** — set `LLM_PROVIDER=anthropic` (~10× faster, paid)
3. **Reduce claims** — set `MAX_CLAIMS_PER_RESPONSE=5`
4. **Disable query expansion** — set `MULTI_QUERY_ENABLED=false`
5. **Disable self-correction** — set `SELF_CORRECTION_ENABLED=false`
6. **Use smaller model** — e.g., `EXTRACTOR_MODEL=llama3.2:1b`

**Cache warmup:** Second requests are much faster — the claim cache and semantic cache mean verified claims are reused instantly.

---

## API Reference

All endpoints at `http://localhost:8080`. Interactive docs: **http://localhost:8080/docs**

### Verification

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/verify` | Verify text (JSON response) |
| `POST` | `/verify/stream` | Verify text (SSE streaming) |
| `POST` | `/v1/chat/completions` | OpenAI-compatible proxy with hallucination detection |
| `POST` | `/v1/messages` | Anthropic-compatible proxy with hallucination detection |

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
  "corrected_text": "Einstein was born in Ulm in 1879.",
  "processing_time_ms": 4230,
  "claims": [
    {
      "id": "...",
      "text": "Einstein was born in Berlin",
      "type": "geographic",
      "category": "GENERAL",
      "stakes": "medium",
      "status": "contradicted",
      "confidence": 0.45,
      "action": "flag",
      "annotation": "[FLAGGED: Einstein was born in Ulm, not Berlin (GENERAL threshold 0.60)]",
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
| `GET` | `/audit/stats` | Aggregate stats (includes `corrected_count`, `flagged_responses`) |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check + stats |
| `GET` | `/cache/stats` | Cache hit rate |
| `POST` | `/cache/clear` | Clear verification cache |

---

## Troubleshooting

### "Request timed out" (Ollama)

1. Make sure Ollama is running: `ollama serve`
2. Make sure the model is downloaded: `ollama pull phi3:mini`
3. Start the backend: `python run_proxy.py`
4. **First request takes 1–3 minutes** — Ollama loads the model. Switch to NVIDIA NIM to avoid this entirely.

### "Backend unreachable"

```bash
python run_proxy.py
# Should print: Proxy ready on 0.0.0.0:8080
```

### "No claims detected"

The text may not contain verifiable factual statements. Try one of the sample texts in the Playground.

### "All claims UNVERIFIABLE"

The knowledge base is empty and Web-RAG is disabled or rate-limited. Populate the KB:
```bash
python ingest_wikipedia.py "Albert Einstein" "Marie Curie" "Penicillin" "COVID-19 vaccine" "Isaac Newton"
```

Or enable Web-RAG: set `WEB_RAG_ENABLED=true` in `.env`.

### Port 8080 already in use

```ini
PROXY_PORT=8081
```

---

## Project Structure

```
hallucination_middleware/
├── proxy.py            FastAPI server, all API endpoints
├── pipeline.py         Main detection pipeline orchestrator
├── claim_extractor.py  LLM-based claim extraction + category labelling
├── verifier.py         Claim verification (KB + Web-RAG fallback)
├── knowledge_base.py   ChromaDB + BM25 hybrid search
├── decision_engine.py  Domain-specific BLOCK/FLAG/ANNOTATE/PASS logic
├── corrector.py        Self-correction loop — rewrites flagged/blocked text
├── mpc_controller.py   MPC receding-horizon refinement (candidate scoring)
├── cache.py            Two-level claim cache (memory/Redis + semantic cache)
├── reranker.py         Cross-encoder reranking (optional)
├── models.py           Pydantic models (incl. MPCCandidate, MPCResult)
├── config.py           Settings from .env
├── audit_trail.py      JSONL audit logging (incl. corrected_count)
├── wikipedia_ingest.py Wikipedia article ingestion
└── web_search.py       Structured Tavily / DuckDuckGo web search

frontend/src/
├── App.jsx             Router + ToastProvider
├── api.js              All API calls with timeout
└── components/
    ├── Playground.jsx   Claim table (category badges) + before/after diff view
    ├── Dashboard.jsx    Charts + live Blocked/Flagged/Corrected KPI cards
    ├── KnowledgeBase.jsx Document management
    ├── AuditLog.jsx     Audit history with export
    ├── Settings.jsx     Config display + cache controls
    ├── Navbar.jsx       Navigation + live health status
    └── Toast.jsx        Global toast notifications

run_proxy.py            Entry point — starts uvicorn server
demo.py                 CLI demo — before/after self-correction panel
benchmark.py            Performance benchmark (p50/p95/p99, throughput, cache)
evaluate.py             Evaluation harness (precision/recall)
eval_cases.yaml         26 test cases (medical, legal, financial, history, science)
ingest_docs.py          CLI for ingesting files, URLs, and raw text
ingest_wikipedia.py     CLI for batch Wikipedia ingestion
ingest_pdfs.py          CLI for ingesting PDF documents
requirements.txt        Python dependencies
.env                    Configuration (edit this file)
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

Runs 4 test cases and prints a claim table + before/after self-correction panel for each.

### Ingest documents via CLI

```bash
# Ingest a directory of .txt / .pdf files
python ingest_docs.py ingest ./docs/

# Ingest a URL
python ingest_docs.py url https://example.com/article

# Ingest raw text
python ingest_docs.py text "Paris is the capital of France." --source geography

# List all documents
python ingest_docs.py list-docs

# Show KB + audit statistics
python ingest_docs.py stats
```

### Run evaluation suite

```bash
python evaluate.py
```

Runs all 26 cases in `eval_cases.yaml` (18 original + 8 domain-specific: medical dosage, wrong birthplace, fake dates, financial, legal) and reports precision/recall per claim type.

### Run performance benchmark

```bash
python benchmark.py --output results.json
```

Outputs p50/p95/p99 latency, throughput (claims/sec), cache hit rate, and per-text breakdown.

### Run with auto-reload

```bash
python run_proxy.py --reload
```
