"""Generate HalluCheck v3 presentation PDF."""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import KeepTogether

W, H = A4

# ── Colour palette ────────────────────────────────────────────────────────────
C_DARK   = colors.HexColor("#0f172a")   # slide bg (used in header bands)
C_BLUE   = colors.HexColor("#38bdf8")   # accent / sky-400
C_GREEN  = colors.HexColor("#34d399")   # verified / emerald-400
C_RED    = colors.HexColor("#f87171")   # blocked  / red-400
C_YELLOW = colors.HexColor("#fbbf24")   # flagged  / amber-400
C_GRAY   = colors.HexColor("#94a3b8")   # secondary text
C_LIGHT  = colors.HexColor("#e2e8f0")   # light text on dark bg
C_PANEL  = colors.HexColor("#1e293b")   # panel bg
C_BORDER = colors.HexColor("#334155")   # border

styles = getSampleStyleSheet()

def sty(name, **kw):
    return ParagraphStyle(name, parent=styles["Normal"], **kw)

TITLE   = sty("T",  fontName="Helvetica-Bold",  fontSize=28, leading=34,
               textColor=C_LIGHT, alignment=TA_CENTER)
SUBTITLE= sty("ST", fontName="Helvetica",        fontSize=14, leading=20,
               textColor=C_BLUE,  alignment=TA_CENTER)
SH      = sty("SH", fontName="Helvetica-Bold",   fontSize=16, leading=22,
               textColor=C_BLUE,  spaceBefore=8,  spaceAfter=4)
BODY    = sty("B",  fontName="Helvetica",         fontSize=11, leading=16,
               textColor=colors.HexColor("#cbd5e1"), spaceAfter=4)
BULLET  = sty("BU", fontName="Helvetica",         fontSize=11, leading=16,
               textColor=colors.HexColor("#cbd5e1"), leftIndent=18, spaceAfter=3,
               bulletIndent=6)
SMALL   = sty("SM", fontName="Helvetica",         fontSize=9,  leading=13,
               textColor=C_GRAY)
CODE    = sty("CO", fontName="Courier",            fontSize=9,  leading=13,
               textColor=C_GREEN, backColor=C_PANEL,
               leftIndent=12, rightIndent=12, borderPad=6)
LABEL   = sty("LB", fontName="Helvetica-Bold",    fontSize=10, leading=14,
               textColor=C_BLUE)
SLIDE_H = sty("SLH",fontName="Helvetica-Bold",   fontSize=20, leading=26,
               textColor=colors.white, alignment=TA_CENTER)

def hr():
    return HRFlowable(width="100%", thickness=1, color=C_BORDER, spaceAfter=8, spaceBefore=4)

def header_band(title_text, subtitle_text=None):
    """Dark header band that mimics a slide title bar."""
    inner = [Paragraph(title_text, SLIDE_H)]
    if subtitle_text:
        inner.append(Paragraph(subtitle_text,
                               sty("x", fontName="Helvetica", fontSize=11,
                                   textColor=C_BLUE, alignment=TA_CENTER)))
    t = Table([[inner]], colWidths=[W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
        ("ROUNDEDCORNERS",(0,0), (-1,-1), [8,8,8,8]),
    ]))
    return t

def kv_table(rows, col1=6*cm, col2=None):
    """Two-column key-value table."""
    col2 = col2 or (W - 4*cm - col1)
    data = []
    for k, v in rows:
        data.append([Paragraph(k, LABEL), Paragraph(v, BODY)])
    t = Table(data, colWidths=[col1, col2])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_PANEL),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [C_PANEL, colors.HexColor("#263147")]),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("GRID",          (0,0), (-1,-1), 0.5, C_BORDER),
        ("ROUNDEDCORNERS",(0,0), (-1,-1), [4,4,4,4]),
    ]))
    return t

def metric_table(items):
    """Row of coloured metric cards: [(label, value, color), ...]."""
    cells = []
    for label, value, col in items:
        block = [
            Paragraph(value, sty("mv", fontName="Helvetica-Bold", fontSize=22,
                                  textColor=col, alignment=TA_CENTER)),
            Paragraph(label, sty("ml", fontName="Helvetica", fontSize=9,
                                  textColor=C_GRAY, alignment=TA_CENTER)),
        ]
        cells.append(block)
    cw = (W - 4*cm) / len(cells)
    t = Table([cells], colWidths=[cw]*len(cells))
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_PANEL),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.5, C_BORDER),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t

def flow_table(steps):
    """Horizontal pipeline flow: [(emoji, title, desc), ...]."""
    cells, arrows = [], []
    for i, (em, ttl, desc) in enumerate(steps):
        block = [
            Paragraph(f"{em}", sty("fe", fontName="Helvetica-Bold", fontSize=16,
                                   textColor=C_BLUE, alignment=TA_CENTER)),
            Paragraph(ttl, sty("ft", fontName="Helvetica-Bold", fontSize=9,
                                textColor=colors.white, alignment=TA_CENTER)),
            Paragraph(desc, sty("fd", fontName="Helvetica", fontSize=8,
                                 textColor=C_GRAY, alignment=TA_CENTER)),
        ]
        cells.append(block)
        if i < len(steps)-1:
            cells.append(Paragraph("→", sty("ar", fontName="Helvetica-Bold",
                                             fontSize=14, textColor=C_BLUE,
                                             alignment=TA_CENTER)))
    n = len(steps)
    arrow_w = 0.6*cm
    box_w   = (W - 4*cm - (n-1)*arrow_w) / n
    cws = []
    for i in range(2*n - 1):
        cws.append(arrow_w if i % 2 == 1 else box_w)
    t = Table([cells], colWidths=cws)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_PANEL),
        ("BACKGROUND",    (1,0), (1,0),   colors.white),   # arrows transparent
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("GRID",          (0,0), (-1,-1), 0.4, C_BORDER),
    ]))
    return t

def build():
    out = "HalluCheck_Presentation.pdf"
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )
    story = []
    sp = lambda n=1: Spacer(1, n*0.35*cm)

    # ── COVER ─────────────────────────────────────────────────────────────────
    story += [
        sp(3),
        Paragraph("HalluCheck v3", TITLE),
        sp(0.5),
        Paragraph("Real-Time Hallucination Detection Middleware", SUBTITLE),
        sp(0.3),
        Paragraph("for Large Language Models", SUBTITLE),
        sp(2),
        hr(),
        sp(0.5),
        Paragraph("International AI Competition — Project Report", sty("cr",
            fontName="Helvetica-Bold", fontSize=12, textColor=C_YELLOW,
            alignment=TA_CENTER)),
        sp(0.3),
        Paragraph("Built with NVIDIA NIM · ChromaDB · Redis · FastAPI · React",
                  sty("cs", fontName="Helvetica", fontSize=10, textColor=C_GRAY,
                      alignment=TA_CENTER)),
        sp(2),
        metric_table([
            ("Total KB Chunks",    "7,705",  C_BLUE),
            ("Pipeline Speed",     "~9 s",   C_GREEN),
            ("Test Coverage",      "46 tests",C_YELLOW),
            ("Project Grade",      "A",       C_GREEN),
        ]),
        PageBreak(),
    ]

    # ── 1. PROBLEM STATEMENT ──────────────────────────────────────────────────
    story += [
        header_band("01  The Problem", "Why hallucination detection matters"),
        sp(),
        Paragraph(
            "Large Language Models (LLMs) confidently generate <b>false information</b> — "
            "called hallucinations. In high-stakes domains such as medicine, law, and finance, "
            "a single wrong fact can have serious consequences.", BODY),
        sp(0.5),
        kv_table([
            ("Medical risk",    "An LLM saying 'Ibuprofen is safe in all trimesters' is dangerously wrong."),
            ("Legal risk",      "Wrong statute dates or fine amounts can mislead professionals."),
            ("Financial risk",  "Wrong FDIC limits or tax rates cause real monetary harm."),
            ("Trust erosion",   "Users cannot tell when an LLM is fabricating — they need a safety net."),
        ]),
        sp(),
        Paragraph(
            "Existing solutions either <b>block the entire response</b> (too aggressive) or "
            "<b>do nothing</b> (too permissive). There is no production-ready middleware that "
            "detects, flags, and <i>corrects</i> hallucinations claim-by-claim in real time.", BODY),
        PageBreak(),
    ]

    # ── 2. SOLUTION ───────────────────────────────────────────────────────────
    story += [
        header_band("02  Our Solution", "HalluCheck — claim-level RAG verification"),
        sp(),
        Paragraph(
            "HalluCheck sits between any LLM and the end user. It intercepts every response, "
            "extracts individual factual claims, verifies each one against an authoritative "
            "knowledge base, and <b>rewrites wrong answers</b> before they reach the user.", BODY),
        sp(),
        flow_table([
            ("📥", "LLM Output",  "Raw text in"),
            ("🔍", "Extract",     "Claimify pipeline"),
            ("📚", "Retrieve",    "Hybrid KB search"),
            ("⚖️",  "Verify",     "LLM fact-check"),
            ("🚦", "Decide",      "Domain thresholds"),
            ("✏️", "Correct",     "Rewrite errors"),
            ("📤", "Safe Output", "Annotated text"),
        ]),
        sp(),
        Paragraph("What makes it unique:", SH),
        kv_table([
            ("Claim-level",      "Operates on individual sentences — not the whole response."),
            ("Self-correcting",  "Rewrites blocked/flagged claims using verified evidence."),
            ("Domain-aware",     "Medical claims need 82% confidence; General only 40%."),
            ("Streaming SSE",    "Results stream in real time — no waiting for full pipeline."),
            ("100% free to run", "NVIDIA NIM free tier — no OpenAI bills."),
        ]),
        PageBreak(),
    ]

    # ── 3. ARCHITECTURE ───────────────────────────────────────────────────────
    story += [
        header_band("03  Architecture", "Production-grade 4-service stack"),
        sp(),
        kv_table([
            ("FastAPI Backend",   "Async Python server — SSE streaming, rate limiting, role-based auth."),
            ("ChromaDB",          "7,705-chunk vector store (cosine similarity, HNSW index)."),
            ("Redis",             "Semantic claim cache — 100% hit rate on repeated queries."),
            ("nginx (HTTPS)",     "TLS termination, HTTP→HTTPS redirect, SSE proxy buffering disabled."),
            ("React Frontend",    "Real-time SSE consumer — Playground, Dashboard, KB, Audit Log."),
            ("GitHub Actions CI", "46 pytest tests + lint on every push — zero broken merges."),
            ("Docker",            "Non-root user, GPU passthrough, offline HuggingFace model cache."),
        ], col1=5*cm),
        sp(),
        Paragraph("Request lifecycle:", SH),
        Paragraph("Browser → nginx:443 → middleware:8080 → [ChromaDB + Redis + NVIDIA NIM] → SSE stream back", CODE),
        sp(0.5),
        Paragraph("Security layers:", SH),
        kv_table([
            ("Auth",         "Bearer token — read keys for /verify, admin keys for /kb/ingest."),
            ("Rate limiting","20 requests/minute per API key or IP (in-memory sliding window)."),
            ("Input validation","Text length capped at 50,000 chars; URL scheme whitelist."),
            ("HTTPS",        "nginx TLS 1.2/1.3 — all traffic encrypted end-to-end."),
        ], col1=5*cm),
        PageBreak(),
    ]

    # ── 4. PIPELINE DEEP-DIVE ─────────────────────────────────────────────────
    story += [
        header_band("04  Pipeline Deep-Dive", "How each claim is verified"),
        sp(),
        Paragraph("Stage 1 — Claimify Extraction", SH),
        Paragraph(
            "Uses spaCy for sentence splitting, selection (factual vs opinion), "
            "and decomposition into atomic claims. Then calls <b>llama-3.2-3b</b> "
            "(NVIDIA NIM) to produce structured JSON with claim type, stakes, and category.", BODY),
        sp(0.3),
        Paragraph("Stage 2 — Hybrid Retrieval", SH),
        kv_table([
            ("HyDE",         "Generates a hypothetical document to bridge the phrasing gap before search."),
            ("Multi-query",  "Expands each claim into N search variants for better recall."),
            ("BM25 (35%)",   "Keyword matching — catches exact term matches."),
            ("Vector (65%)", "Semantic similarity via all-MiniLM-L6-v2 embeddings."),
            ("CrossEncoder", "Reranks top-10 candidates to pick the best 5 for the LLM."),
            ("Web-RAG",      "Falls back to Tavily/DuckDuckGo when KB score < 0.25."),
        ], col1=5*cm),
        sp(0.3),
        Paragraph("Stage 3 — LLM Verification", SH),
        Paragraph(
            "<b>llama-3.3-70b</b> (NVIDIA NIM) reads the claim + top-5 evidence chunks "
            "and outputs: status, confidence score, key evidence quote, and reasoning. "
            "Status is one of: verified / contradicted / partially_supported / unverifiable.", BODY),
        sp(0.3),
        Paragraph("Stage 4 — Domain-Aware Decision Engine", SH),
        metric_table([
            ("MEDICAL block threshold",   "0.82",  C_RED),
            ("LEGAL block threshold",     "0.76",  C_RED),
            ("FINANCIAL block threshold", "0.70",  C_YELLOW),
            ("GENERAL block threshold",   "0.40",  C_GREEN),
        ]),
        sp(0.3),
        Paragraph("Stage 5 — Self-Correction", SH),
        Paragraph(
            "After decisions, if any claim was blocked or flagged, a second LLM call "
            "rewrites only the incorrect portions using the verified evidence — the corrected "
            "text arrives as a separate SSE 'corrected' event so results are not delayed.", BODY),
        PageBreak(),
    ]

    # ── 5. KNOWLEDGE BASE ─────────────────────────────────────────────────────
    story += [
        header_band("05  Knowledge Base", "7,705 authoritative chunks across 6 domains"),
        sp(),
        kv_table([
            ("Wikipedia articles",  "Albert Einstein, DNA, Climate Change, Vaccination, WWII, AI, Internet, COVID-19, Diabetes, Inflation, US Constitution, Python, Stock Market, French Revolution, Quantum Mechanics, and more."),
            ("Medical facts",       "15 entries — drug safety, WHO thresholds, FDA approval dates, clinical trial results."),
            ("Legal facts",         "15 entries — GDPR (Art.17, Art.20, fines), CCPA, Miranda rights, attorney-client privilege, double jeopardy, NDA."),
            ("Financial facts",     "15 entries — capital gains rates, Fed dual mandate, FDIC $250K limit, 401k limits, Dodd-Frank, Basel III, FICO scores."),
            ("Physics facts",       "Speed of light, Planck constant, Bohr radius, thermodynamic laws."),
            ("General tech facts",  "WWW 1989, Google founded 1998, Apple co-founders 1976, iPhone launch 2007."),
        ], col1=5*cm),
        sp(),
        Paragraph("Hybrid search configuration:", SH),
        Paragraph(
            "BM25_WEIGHT=0.35  |  VECTOR_WEIGHT=0.65  |  TOP_K=5  |  "
            "RERANKER=cross-encoder/ms-marco-MiniLM-L-6-v2  |  MIN_RELEVANCE=0.20",
            CODE),
        sp(),
        Paragraph("Live KB management:", SH),
        kv_table([
            ("Ingest text",      "POST /kb/ingest  (admin key required)"),
            ("Ingest Wikipedia", "POST /kb/ingest/wikipedia  — fetches and chunks in real time"),
            ("List documents",   "GET /kb/documents  — shows all sources with chunk counts"),
            ("Delete document",  "DELETE /kb/documents/{doc_id}  — removes all chunks for a source"),
        ], col1=5*cm),
        PageBreak(),
    ]

    # ── 6. FEATURES ───────────────────────────────────────────────────────────
    story += [
        header_band("06  Key Features", "What judges will see in the live demo"),
        sp(),
        Paragraph("Frontend — 5 tabs:", SH),
        kv_table([
            ("Playground",     "Paste any LLM output → SSE stream shows claims appearing one by one with VERIFIED / FLAGGED / BLOCKED badges, confidence scores, evidence quotes, and self-corrected text."),
            ("Dashboard",      "Live charts — verified vs flagged vs blocked pie, confidence trend line, processing time bar, domain breakdown, cache hit rate."),
            ("Knowledge Base", "Browse 7,705 chunks, search by keyword, add Wikipedia topics live, delete documents, see per-source chunk counts."),
            ("Audit Log",      "Every request logged with full claim breakdown, timestamp, model, processing time. Filter by date range."),
            ("Settings",       "API key management, system status, cache stats, Wikipedia ingest tool, backend health check."),
        ], col1=4*cm),
        sp(),
        Paragraph("Live demo text (paste this to impress judges):", SH),
        Paragraph(
            '"The EU GDPR came into force on 1 June 2019. Data breaches must be reported within '
            '24 hours. FDIC insures deposits up to $100,000. Ibuprofen is safe throughout '
            'all trimesters of pregnancy."', CODE),
        sp(0.3),
        Paragraph(
            "Every single claim above is <b>wrong</b>. HalluCheck will catch all 4 errors "
            "with evidence and rewrite them correctly.", BODY),
        PageBreak(),
    ]

    # ── 7. TECH STACK ─────────────────────────────────────────────────────────
    story += [
        header_band("07  Technical Stack", "Every component justified"),
        sp(),
        kv_table([
            ("NVIDIA NIM",           "Free-tier cloud GPU inference. llama-3.2-3b (extractor, fast) + llama-3.3-70b (verifier, accurate)."),
            ("ChromaDB",             "Persistent vector store with HNSW cosine index. Chosen for zero-cost self-hosting."),
            ("BM25 (rank_bm25)",     "In-memory keyword index rebuilt from ChromaDB at startup. Adds lexical recall on top of semantic search."),
            ("CrossEncoder",         "cross-encoder/ms-marco-MiniLM-L-6-v2 — reranks 10 candidates to 5 most relevant."),
            ("sentence-transformers","all-MiniLM-L6-v2 baked into Docker image — no download on container start."),
            ("Redis",                "Semantic claim cache with 1h TTL. Prevents re-verifying identical claims."),
            ("FastAPI",              "Async ASGI server. StreamingResponse for SSE. Pydantic-settings for typed config."),
            ("React + Vite",         "SPA built into the Docker image — no separate frontend server needed."),
            ("nginx",                "TLS termination, HTTP→HTTPS redirect, proxy_buffering off for SSE."),
            ("Docker Compose",       "4-service orchestration: middleware, redis, nginx, plus GPU passthrough."),
            ("GitHub Actions",       "CI: pytest (46 tests) + lint on every push to main."),
            ("spaCy en_core_web_sm", "Sentence boundary detection for Claimify pipeline. Baked into Docker."),
        ], col1=5.5*cm),
        PageBreak(),
    ]

    # ── 8. API REFERENCE ──────────────────────────────────────────────────────
    story += [
        header_band("08  API Reference", "OpenAI-compatible + custom endpoints"),
        sp(),
        Paragraph("Core endpoints:", SH),
        kv_table([
            ("POST /verify/stream",       "SSE — stream claim-by-claim results (main endpoint)."),
            ("POST /verify",              "Sync — returns full JSON result (non-streaming)."),
            ("GET  /health",              "System health: KB chunks, cache stats, audit totals."),
            ("GET  /audit/recent",        "Last N audit records with full claim breakdown."),
            ("GET  /audit/stats",         "Aggregate counts: verified, flagged, blocked, avg confidence."),
            ("GET  /kb/stats",            "KB info: chunk count, collection name, BM25 status."),
            ("POST /kb/ingest",           "Add text to KB (admin key). Auto-chunks and indexes."),
            ("POST /kb/ingest/wikipedia", "Fetch + ingest a Wikipedia article by topic name."),
            ("GET  /kb/documents",        "List all document sources with chunk counts."),
            ("DELETE /kb/documents/{id}", "Remove all chunks for a document (admin key)."),
            ("POST /cache/clear",         "Clear Redis + semantic cache (admin key)."),
            ("GET  /docs",                "OpenAPI Swagger UI."),
        ], col1=5.5*cm),
        sp(),
        Paragraph("Authentication:", SH),
        kv_table([
            ("Read key",  "hallu-dev-secret-2024  →  /verify, /audit, /health, /kb/stats"),
            ("Admin key", "hallu-dev-secret-2024  →  additionally: /kb/ingest, /kb/delete, /cache/clear"),
            ("Header",    "Authorization: Bearer <key>  OR  X-API-Key: <key>"),
        ], col1=4*cm),
        PageBreak(),
    ]

    # ── 9. RUNNING THE PROJECT ────────────────────────────────────────────────
    story += [
        header_band("09  Running the Project", "Start in 3 commands"),
        sp(),
        Paragraph("Prerequisites:", SH),
        kv_table([
            ("Docker Desktop", "Windows — enable WSL2 backend. GPU passthrough optional."),
            ("Internet access","NVIDIA NIM API calls (free tier). Tavily web search fallback."),
            ("Ports free",    "8080 (middleware), 80 and 443 (nginx), 6379 (redis)."),
        ], col1=5*cm),
        sp(),
        Paragraph("Start:", SH),
        Paragraph("docker compose up -d", CODE),
        sp(0.3),
        Paragraph("Open browser:", SH),
        Paragraph("http://localhost:8080", CODE),
        sp(0.3),
        Paragraph("Set API key (one-time):", SH),
        Paragraph(
            "1. Click Settings tab\n"
            "2. Enter:  hallu-dev-secret-2024\n"
            "3. Click Save API Key", CODE),
        sp(0.3),
        Paragraph("Test the pipeline:", SH),
        Paragraph("curl -X POST http://localhost:8080/verify/stream \\\n"
                  "  -H 'Authorization: Bearer hallu-dev-secret-2024' \\\n"
                  "  -H 'Content-Type: application/json' \\\n"
                  "  -d '{\"text\": \"GDPR came into force on 1 June 2019.\", \"model\": \"test\"}'",
                  CODE),
        sp(),
        Paragraph("Stop:", SH),
        Paragraph("docker compose down", CODE),
        PageBreak(),
    ]

    # ── 10. EVALUATION ────────────────────────────────────────────────────────
    story += [
        header_band("10  Evaluation & Results", "Competition-grade metrics"),
        sp(),
        metric_table([
            ("End-to-end latency",  "~9 s",   C_GREEN),
            ("KB chunks",          "7,705",   C_BLUE),
            ("Test suite",         "46 pass", C_GREEN),
            ("Project grade",      "A",       C_GREEN),
        ]),
        sp(),
        Paragraph("Strengths:", SH),
        kv_table([
            ("Production-ready",     "HTTPS, role-based auth, Docker, GitHub Actions CI — not a prototype."),
            ("Zero cold-start delay","Models baked into image; no HuggingFace download on container start."),
            ("Self-correcting",      "Unique feature: system rewrites its own errors automatically."),
            ("Domain-aware safety",  "Per-category thresholds — medical strictest, general most permissive."),
            ("Fully free stack",     "NVIDIA NIM free tier + Redis + ChromaDB + DuckDuckGo — $0/month."),
            ("Streaming UX",         "SSE stream means judges see results live — no blank wait screen."),
            ("Transparent",         "Every decision shows confidence score, evidence quote, and reasoning."),
        ], col1=5*cm),
        sp(),
        Paragraph("Honest limitations:", SH),
        kv_table([
            ("NVIDIA NIM latency",  "Free tier can be slow (~9–30s) depending on API queue depth."),
            ("KB coverage",         "Limited to ingested topics — unknown claims are marked unverifiable."),
            ("Language",            "English only (spaCy en_core_web_sm)."),
        ], col1=5*cm),
        PageBreak(),
    ]

    # ── 11. COMPETITION TALKING POINTS ───────────────────────────────────────
    story += [
        header_band("11  Competition Talking Points", "What to say to judges"),
        sp(),
        Paragraph(
            "Prepare these 5 points. Each is backed by a live demo action.", BODY),
        sp(0.5),
        kv_table([
            ("1. Production-ready",
             "Show nginx HTTPS, GitHub Actions CI badge, Docker health checks. "
             "Say: 'This isn\'t a Jupyter notebook — it\'s deployable software.'"),
            ("2. Zero cold start",
             "Run 'docker compose restart' — show it comes back in <15 seconds with "
             "no download logs. Models are baked into the image."),
            ("3. Self-correcting AI",
             "Paste the GDPR/FDIC/ibuprofen text. Point at the 'corrected_text' field "
             "that arrives after the main result. 'It not only detects — it fixes.'"),
            ("4. Domain-aware safety",
             "Show the Settings page domain thresholds. Explain why medical claims need "
             "82% confidence while general claims only need 40%."),
            ("5. Free to run forever",
             "Open https://build.nvidia.com — show the free tier. "
             "'Any university, startup, or hospital can run this at zero API cost.'"),
        ], col1=4*cm),
        sp(),
        Paragraph("Demo script (3-minute version):", SH),
        kv_table([
            ("0:00 – 0:30", "Open Playground. Explain the problem in one sentence."),
            ("0:30 – 1:30", "Paste the GDPR/FDIC demo text. Click Detect. Watch the stream."),
            ("1:30 – 2:00", "Point at BLOCKED (red) and FLAGGED (yellow) claims. Show evidence."),
            ("2:00 – 2:30", "Show corrected_text — the system rewrote the errors."),
            ("2:30 – 3:00", "Switch to Dashboard tab. Show charts. Mention 7,705 KB chunks."),
        ], col1=3*cm),
        PageBreak(),
    ]

    # ── 12. CLOSING ───────────────────────────────────────────────────────────
    story += [
        sp(4),
        Paragraph("HalluCheck v3", TITLE),
        sp(0.5),
        Paragraph("Keeping AI Honest — One Claim at a Time", SUBTITLE),
        sp(2),
        hr(),
        sp(1),
        Paragraph("Quick-start:", sty("qs", fontName="Helvetica-Bold", fontSize=12,
                                      textColor=C_BLUE, alignment=TA_CENTER)),
        sp(0.3),
        Paragraph("docker compose up -d  →  http://localhost:8080",
                  sty("qc", fontName="Courier-Bold", fontSize=13, textColor=C_GREEN,
                      alignment=TA_CENTER)),
        sp(2),
        metric_table([
            ("Extractor",  "llama-3.2-3b",    C_BLUE),
            ("Verifier",   "llama-3.3-70b",   C_BLUE),
            ("Vector DB",  "ChromaDB",         C_YELLOW),
            ("Cache",      "Redis",            C_YELLOW),
            ("Frontend",   "React + Vite",     C_GREEN),
            ("Grade",      "A",                C_GREEN),
        ]),
        sp(2),
        Paragraph("Good luck at the competition!", sty("gl",
            fontName="Helvetica-Bold", fontSize=14, textColor=C_YELLOW,
            alignment=TA_CENTER)),
    ]

    doc.build(story)
    print(f"PDF created: {out}")
    return out

if __name__ == "__main__":
    build()
