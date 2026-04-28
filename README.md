# HalluCheck v4

A production-grade hallucination detection middleware that sits between your application and any LLM API. It intercepts responses, verifies factual claims against live web sources, and returns BLOCK / FLAG / ANNOTATE / PASS decisions with source citations — without changing your existing API calls.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Set API keys in .env
#    Required: NVIDIA_NIM_API_KEY, TAVILY_API_KEY
#    Optional: TOGETHER_API_KEY (fallback), REDIS_URL

# 3. Start the proxy
uvicorn hallucination_middleware.proxy:app --host 0.0.0.0 --port 8080

# 4. Point your app at the proxy
#    OpenAI-compatible:   http://localhost:8080/v1/chat/completions
#    Anthropic-compatible: http://localhost:8080/v1/messages
```

---

## How It Works

Every LLM response passes through a 7-stage async pipeline:

```
Input text
    │
    ▼
[1] Coreference Resolution      pronouns → named entities ("He won" → "Einstein won")
    │
    ▼
[2] Claim Extraction            Claimify: split → select (with kind tag) → decompose
                                OPINION / PREDICTION / CREATIVE → auto-PASS, no web search
    │
    ▼
[3] Web Verification            Tavily + DuckDuckGo → NLI (DeBERTa-v3) → LLM judge
                                Source credibility scoring, cross-encoder reranker
    │
    ▼
[4] Decision Engine             BLOCK / FLAG / ANNOTATE / PASS (domain-aware thresholds)
                                Cross-claim internal contradiction detection
    │
    ▼
[5] HMM Cascade Detection       2-state Gaussian HMM + Viterbi — reliability across claims
    │
    ▼
[6] Self-Correction             LLM rewrites flagged claims with evidence, NLI-gated
    │
    ▼
[7] MPC Refinement              Receding-horizon candidate selection (NLI scored, no web cost)
    │
    ▼
HallucinationAudit returned to caller
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Tested on 3.11 |
| NVIDIA NIM API key | Free tier — [build.nvidia.com](https://build.nvidia.com) |
| Tavily API key | Free tier — [tavily.com](https://tavily.com) |
| Together AI key | Optional — auto-activates as fallback on NIM 429/503 |
| Redis | Optional — falls back to in-memory cache |
| CUDA GPU | Optional — DeBERTa NLI + reranker run on CPU otherwise |
| spaCy `en_core_web_sm` | `python -m spacy download en_core_web_sm` |

---

## Installation

```bash
git clone https://github.com/kuldeepkumar09/Hallucination-detection.git
cd Hallucination-detection
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

---

## Configuration

All settings live in `.env`. Required keys:

```env
# LLM Provider: nvidia_nim | together | anthropic | ollama
LLM_PROVIDER=nvidia_nim
NVIDIA_NIM_API_KEY=nvapi-your-key-here
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1

EXTRACTOR_MODEL=meta/llama-3.1-8b-instruct
VERIFIER_MODEL=meta/llama-3.3-70b-instruct

TAVILY_API_KEY=tvly-your-key-here

# Optional fallback
TOGETHER_API_KEY=tgp_your-key-here
FALLBACK_ENABLED=true

# Security
API_KEY=your-read-key
ADMIN_KEY=your-admin-key
```

Key feature flags:

| Variable | Default | Description |
|---|---|---|
| `BLOCK_THRESHOLD` | `0.50` | Global block confidence cutoff |
| `FLAG_THRESHOLD` | `0.60` | Global flag confidence cutoff |
| `NLI_ENABLED` | `true` | DeBERTa-v3 entailment scoring |
| `HMM_ENABLED` | `true` | Cascade hallucination detection |
| `SELF_CORRECTION_ENABLED` | `true` | LLM rewrites flagged claims |
| `MPC_ENABLED` | `true` | Receding-horizon sentence rewriting |
| `RERANKER_ENABLED` | `true` | Cross-encoder evidence reranking |
| `COREF_ENABLED` | `true` | Pronoun resolution before extraction |
| `CACHE_ENABLED` | `true` | Semantic + claim cache |
| `CACHE_TTL_SECONDS` | `3600` | Cache lifetime |
| `MAX_CLAIMS_PER_RESPONSE` | `25` | Cap on extracted claims |
| `REQUEST_TIMEOUT` | `60.0` | Per-request timeout (seconds) |

Full reference: `hallucination_middleware/config.py`.

---

## API Reference

All endpoints require `x-api-key` header (or `Authorization: Bearer <key>`).
Admin endpoints additionally require an admin-level key.

### Verification

#### `POST /verify`
Run text through the full pipeline.

```bash
curl -X POST http://localhost:8080/verify \
  -H "x-api-key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "Einstein won the Nobel Prize for his theory of relativity."}'
```

Response:
```json
{
  "request_id": "abc123",
  "total_claims": 1,
  "flagged_count": 1,
  "blocked_count": 0,
  "overall_confidence": 0.41,
  "annotated_text": "Einstein won the Nobel Prize for his theory of relativity.\n\n---\n⚠ [FLAG] ...",
  "corrected_text": "Einstein won the Nobel Prize for the photoelectric effect.",
  "hmm_cascade_detected": false,
  "processing_time_ms": 3820
}
```

#### `POST /verify/stream`
SSE streaming — events arrive as each claim is verified:

```
event: extracting       {"claim_count": 3}
event: claim_verified   {"claim": "...", "action": "flag", "confidence": 0.41}
event: done             {"flagged_count": 1, "blocked_count": 0}
event: corrected        {"corrected_text": "..."}
```

#### `POST /v1/chat/completions`
OpenAI-compatible drop-in. Adds `hallucheck_audit` to the response object.

#### `POST /v1/messages`
Anthropic-compatible drop-in.

---

### Benchmark Evaluation

#### `POST /evaluate`
Ground-truth benchmark — 44 labelled claims (standard + adversarial).

```bash
curl -X POST http://localhost:8080/evaluate \
  -H "x-api-key: your-key" \
  -d '{"max_claims": 20}'    # omit for full run
```

Returns: `precision`, `recall`, `f1`, `accuracy`, `tp`, `fp`, `tn`, `fn`, `details[]`

#### `POST /evaluate/llm`
**Empirical F1** — sends prompts that LLMs are known to hallucinate on to the configured LLM provider, then runs actual responses through the pipeline. Measures real-world detection performance, not synthetic benchmarks.

```bash
curl -X POST http://localhost:8080/evaluate/llm \
  -H "x-api-key: your-key" \
  -d '{"max_prompts": 10}'
```

Returns: same metrics as `/evaluate` plus `llm_provider`, `model`, `sample_outputs[]`

---

### Knowledge Base (Admin)

```bash
# Ingest text
curl -X POST http://localhost:8080/kb/ingest \
  -H "x-api-key: admin-key" \
  -d '{"text": "...", "source": "my-doc"}'

# Ingest Wikipedia
curl -X POST http://localhost:8080/kb/ingest/wikipedia \
  -H "x-api-key: admin-key" \
  -d '{"topic": "Albert Einstein"}'

# Ingest PDF
curl -X POST http://localhost:8080/kb/ingest/pdf \
  -H "x-api-key: admin-key" \
  -F "file=@/path/to/doc.pdf"

# List documents
curl http://localhost:8080/kb/documents -H "x-api-key: your-key"

# Delete a document
curl -X DELETE http://localhost:8080/kb/documents/DOC_ID \
  -H "x-api-key: admin-key"
```

---

### Audit & Cache

```bash
curl http://localhost:8080/audit/recent         -H "x-api-key: your-key"
curl http://localhost:8080/audit/stats          -H "x-api-key: your-key"
curl http://localhost:8080/audit/stats/categories -H "x-api-key: your-key"
curl http://localhost:8080/cache/stats          -H "x-api-key: your-key"
curl -X POST http://localhost:8080/cache/clear  -H "x-api-key: admin-key"
```

---

## Load Testing

```bash
# Built-in async load test — no extra dependencies
python load_test.py \
  --url http://localhost:8080 \
  --key your-key \
  --concurrency 20 \
  --requests 200

# Example output:
# Requests:     200 / 200 succeeded
# Duration:     41.3s
# RPS:          4.8
# P50 latency:  3.2s
# P90 latency:  7.1s
# P99 latency:  12.4s
# Error rate:   0.5%
```

---

## Decision Logic

| Condition | Action |
|---|---|
| Claim type = OPINION / PREDICTION / CREATIVE | AUTO-PASS |
| Contradicted + CRITICAL or HIGH stakes | BLOCK |
| Contradicted + medium / low stakes | FLAG |
| No evidence found (unverifiable) | FLAG |
| Partially supported | FLAG |
| Confidence below flag threshold | FLAG |
| Fully verified | ANNOTATE or PASS |
| Same-subject conflicting dates across claims | FLAG (internal contradiction) |

Domain-specific thresholds (stricter for medical/legal):

| Domain | Block at | Flag at |
|---|---|---|
| MEDICAL | < 0.65 | < 0.75 |
| LEGAL | < 0.60 | < 0.70 |
| FINANCIAL | < 0.58 | < 0.65 |
| GENERAL | < 0.40 | < 0.55 |

A single Tier-1 source (Wikipedia, .gov, Reuters — credibility ≥ 0.85) is sufficient to validate a contradiction. Lower-credibility sources require 2+ independent domains.

---

## Project Structure

```
hallucination_middleware/
├── proxy.py              FastAPI server — all HTTP endpoints
├── pipeline.py           7-stage async orchestrator
├── config.py             All settings (pydantic-settings, .env)
├── models.py             Pydantic data models
├── claim_extractor.py    Claimify pipeline (split → select → decompose → extract)
├── verifier.py           Web retrieval + NLI scoring + LLM judge
├── decision_engine.py    Decision matrix + cross-claim contradiction check
├── corrector.py          Self-correction loop (NLI-gated)
├── mpc_controller.py     Model Predictive Control rewriter
├── nli_scorer.py         DeBERTa-v3 entailment scorer
├── reranker.py           MS-MARCO cross-encoder reranker
├── knowledge_base.py     WebOnlyKB — Tavily + DuckDuckGo (no local vector store)
├── web_search.py         Structured web search (Tavily / DuckDuckGo)
├── source_credibility.py Domain trust tiers + adaptive contradiction gate
├── cache.py              Semantic cache + Redis/in-memory fallback
├── audit_trail.py        Append-only JSONL audit log
├── evaluation.py         Ground-truth benchmark (44 claims) + empirical LLM eval
├── multilingual.py       Multi-language input handling
├── security.py           Auth + input validation
├── core/
│   ├── coref_handler.py  Coreference resolution (coreferee + NER fallback, 60-token window)
│   └── domain_router.py  MEDICAL / LEGAL / FINANCIAL / GENERAL routing
├── engine/
│   ├── hmm_reliability.py  2-state Gaussian HMM cascade detector + Viterbi
│   ├── reward_system.py    Power-law quality-speed reward J(q,s)
│   └── viterbi_decoding.py
└── ingestion/
    ├── medical_ingest.py
    ├── legal_ingest.py
    └── financial_ingest.py

load_test.py              Async load test (concurrency, RPS, P50/P90/P99)
```

---

## Benchmark

Run `POST /evaluate` for the 44-claim ground-truth benchmark.  
Run `POST /evaluate/llm` for empirical F1 on real LLM-generated outputs.

Expected ranges (live web, Tavily):

| Metric | Standard benchmark | Adversarial benchmark |
|---|---|---|
| Precision | 0.80 – 0.92 | 0.70 – 0.85 |
| Recall | 0.70 – 0.85 | 0.65 – 0.80 |
| F1 | 0.75 – 0.88 | 0.67 – 0.82 |

---

## Limitations

- Claims about events from the last 24–48 hours may be UNVERIFIABLE (Tavily crawl delay)
- Niche facts with no web presence are marked UNVERIFIABLE, never falsely BLOCKED
- Self-correction reduces errors but can occasionally rephrase incorrectly
- F1 varies with Tavily result quality and NIM rate-limit availability

---

## License

MIT
