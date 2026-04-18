"""
Hallucination Detection — Live Monitoring Dashboard

Run:  streamlit run dashboard.py

Tabs:
  1. Overview   — aggregate KPIs, confidence trend, action breakdown
  2. Claims     — claim type / verification status breakdown, frequent flags
  3. Knowledge Base — source stats, file/URL/text upload
  4. Live Feed  — last 50 requests, auto-refreshed every 5 s
"""
import json
import os
from collections import Counter
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Hallucination Detector",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUDIT_PATH = os.getenv("AUDIT_LOG_PATH", "./audit_trail.jsonl")


@st.cache_data(ttl=5)
def load_audit(path: str = AUDIT_PATH):
    p = Path(path)
    if not p.exists():
        return []
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def get_kb():
    from hallucination_middleware import KnowledgeBase  # noqa: PLC0415
    return KnowledgeBase()


def aggregate(entries: list) -> dict:
    if not entries:
        return {}
    total = len(entries)
    blocked = sum(1 for e in entries if e.get("response_blocked"))
    avg_conf = sum(e.get("overall_confidence", 0) for e in entries) / total
    avg_ms = sum(e.get("processing_time_ms", 0) for e in entries) / total
    total_claims = sum(e.get("total_claims", 0) for e in entries)
    return {
        "total_requests": total,
        "blocked_responses": blocked,
        "blocked_pct": round(blocked / total * 100, 1),
        "avg_confidence": round(avg_conf, 3),
        "avg_processing_ms": round(avg_ms, 1),
        "total_claims": total_claims,
    }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🔍 Hallucination Detector")
    st.caption("Real-time LLM output verification")
    st.divider()
    auto_refresh = st.toggle("Auto-refresh (5s)", value=True)
    if st.button("Clear cache now"):
        load_audit.clear()
        st.success("Cache cleared")
    st.divider()
    st.caption(f"Audit log: `{AUDIT_PATH}`")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🔎 Claims", "📚 Knowledge Base", "📡 Live Feed"])

# ===========================================================================
# TAB 1 — Overview
# ===========================================================================

with tab1:
    entries = load_audit()
    agg = aggregate(entries)

    if not entries:
        st.info("No audit entries yet. Run `python demo.py` or start the proxy and send a request.")
    else:
        # KPI cards
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Requests", agg["total_requests"])
        c2.metric("Blocked Responses", agg["blocked_responses"],
                  delta=f"{agg['blocked_pct']}%", delta_color="inverse")
        c3.metric("Avg Confidence", f"{agg['avg_confidence']:.2f}")
        c4.metric("Avg Processing", f"{agg['avg_processing_ms']:.0f} ms")
        c5.metric("Total Claims", agg["total_claims"])

        st.divider()

        col_left, col_right = st.columns(2)

        # Confidence over time
        with col_left:
            st.subheader("Confidence Over Time")
            conf_data = [
                {"Request": i + 1, "Confidence": e.get("overall_confidence", 0),
                 "Blocked": e.get("response_blocked", False)}
                for i, e in enumerate(entries[-100:])
            ]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[d["Request"] for d in conf_data],
                y=[d["Confidence"] for d in conf_data],
                mode="lines+markers",
                name="Confidence",
                marker=dict(
                    color=["red" if d["Blocked"] else "steelblue" for d in conf_data],
                    size=7,
                ),
                line=dict(color="steelblue", width=1.5),
            ))
            fig.add_hline(y=0.6, line_dash="dash", line_color="orange",
                          annotation_text="Flag threshold")
            fig.add_hline(y=0.25, line_dash="dash", line_color="red",
                          annotation_text="Block threshold")
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                               yaxis_range=[0, 1.05])
            st.plotly_chart(fig, use_container_width=True)

        # Action distribution
        with col_right:
            st.subheader("Action Distribution")
            action_counts: Counter = Counter()
            for e in entries:
                for c in e.get("claims", []):
                    action_counts[c.get("action", "unknown")] += 1

            if action_counts:
                colors = {"pass": "#2ecc71", "annotate": "#3498db",
                          "flag": "#f39c12", "block": "#e74c3c"}
                labels = list(action_counts.keys())
                values = list(action_counts.values())
                fig2 = go.Figure(go.Pie(
                    labels=labels, values=values,
                    marker_colors=[colors.get(l, "#95a5a6") for l in labels],
                    hole=0.4,
                ))
                fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.write("No claims yet.")

        # Processing time histogram
        st.subheader("Processing Time Distribution")
        times = [e.get("processing_time_ms", 0) for e in entries if e.get("processing_time_ms")]
        if times:
            fig3 = px.histogram(x=times, nbins=30, labels={"x": "Processing Time (ms)"},
                                color_discrete_sequence=["steelblue"])
            fig3.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig3, use_container_width=True)

# ===========================================================================
# TAB 2 — Claims Analysis
# ===========================================================================

with tab2:
    entries = load_audit()
    if not entries:
        st.info("No audit data yet.")
    else:
        all_claims = [c for e in entries for c in e.get("claims", [])]

        if not all_claims:
            st.info("No claims found in audit log.")
        else:
            col1, col2 = st.columns(2)

            # Claim type breakdown
            with col1:
                st.subheader("Claim Types")
                type_counts: Counter = Counter(c.get("type", "unknown") for c in all_claims)
                fig = px.pie(names=list(type_counts.keys()), values=list(type_counts.values()),
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, use_container_width=True)

            # Verification status breakdown
            with col2:
                st.subheader("Verification Status")
                status_counts: Counter = Counter(c.get("status", "unknown") for c in all_claims)
                status_colors = {
                    "verified": "#2ecc71", "contradicted": "#e74c3c",
                    "unverifiable": "#f39c12", "partially_supported": "#e67e22",
                }
                fig2 = px.pie(
                    names=list(status_counts.keys()),
                    values=list(status_counts.values()),
                    color=list(status_counts.keys()),
                    color_discrete_map=status_colors,
                )
                fig2.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, use_container_width=True)

            # Most flagged/blocked claims
            st.subheader("Most Frequently Flagged / Blocked Claims")
            problem_claims = [
                c for c in all_claims if c.get("action") in ("flag", "block")
            ]
            text_counts: Counter = Counter(c.get("text", "")[:80] for c in problem_claims)
            if text_counts:
                top = text_counts.most_common(15)
                fig3 = px.bar(
                    x=[t[1] for t in top],
                    y=[t[0] for t in top],
                    orientation="h",
                    labels={"x": "Count", "y": "Claim"},
                    color_discrete_sequence=["#e74c3c"],
                )
                fig3.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig3, use_container_width=True)

            # Stakes distribution
            st.subheader("Stakes Distribution")
            stakes_counts: Counter = Counter(c.get("stakes", "unknown") for c in all_claims)
            stakes_order = ["critical", "high", "medium", "low"]
            stakes_data = {s: stakes_counts.get(s, 0) for s in stakes_order}
            fig4 = px.bar(
                x=list(stakes_data.keys()),
                y=list(stakes_data.values()),
                color=list(stakes_data.keys()),
                color_discrete_map={"critical": "#e74c3c", "high": "#e67e22",
                                    "medium": "#f39c12", "low": "#2ecc71"},
                labels={"x": "Stakes Level", "y": "Count"},
            )
            fig4.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                               showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)

# ===========================================================================
# TAB 3 — Knowledge Base
# ===========================================================================

with tab3:
    st.subheader("Knowledge Base Status")

    try:
        kb = get_kb()
        kb_s = kb.stats()
        doc_stats = kb.get_document_stats()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Chunks", kb_s["total_chunks"])
        c2.metric("BM25", "Enabled" if kb_s.get("bm25_enabled") else "Disabled")
        c3.metric("BM25 Indexed", kb_s.get("bm25_indexed", 0))

        # Per-source table
        if doc_stats["by_source"]:
            st.divider()
            st.subheader("Documents by Source")
            src_items = sorted(doc_stats["by_source"].items(), key=lambda x: -x[1])
            fig = px.bar(
                x=[s[1] for s in src_items],
                y=[s[0][:50] for s in src_items],
                orientation="h",
                labels={"x": "Chunks", "y": "Source"},
                color_discrete_sequence=["#3498db"],
            )
            fig.update_layout(height=max(250, len(src_items) * 28),
                               margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Upload section
        st.divider()
        st.subheader("Add Documents")

        up_col1, up_col2 = st.columns(2)

        with up_col1:
            st.markdown("**Upload a file** (.txt or .pdf)")
            uploaded = st.file_uploader("Choose file", type=["txt", "pdf"])
            if uploaded and st.button("Ingest file"):
                import tempfile  # noqa: PLC0415
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = tmp.name
                try:
                    chunks = kb.ingest_file(tmp_path)
                    st.success(f"Ingested {chunks} chunks from '{uploaded.name}'")
                    load_audit.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Error: {exc}")
                finally:
                    os.unlink(tmp_path)

        with up_col2:
            st.markdown("**Ingest a URL**")
            url_input = st.text_input("URL", placeholder="https://example.com/article")
            url_source = st.text_input("Source label (optional)")
            if url_input and st.button("Fetch & ingest"):
                import asyncio  # noqa: PLC0415
                with st.spinner("Fetching ..."):
                    try:
                        chunks = asyncio.run(kb.ingest_url(url_input, source=url_source or url_input))
                        st.success(f"Ingested {chunks} chunks from URL")
                        load_audit.clear()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Error: {exc}")

        st.divider()
        st.subheader("Paste text directly")
        raw_text = st.text_area("Text to ingest", height=120)
        raw_source = st.text_input("Source label", value="manual_input")
        if raw_text and st.button("Ingest text"):
            chunks = kb.ingest_text(raw_text, source=raw_source)
            st.success(f"Ingested {chunks} chunks")

    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not connect to knowledge base: {exc}")
        st.info("Make sure ANTHROPIC_API_KEY is set in your .env file.")

# ===========================================================================
# TAB 4 — Live Feed
# ===========================================================================

with tab4:
    entries = load_audit()

    st.subheader(f"Recent Requests (last {min(50, len(entries))})")
    if auto_refresh:
        st.caption("Auto-refreshing every 5 seconds ...")

    if not entries:
        st.info("No requests yet.")
    else:
        recent = list(reversed(entries[-50:]))
        for entry in recent:
            blocked = entry.get("response_blocked", False)
            conf = entry.get("overall_confidence", 0)
            icon = "BLOCKED" if blocked else ("WARNING" if conf < 0.6 else "OK")
            label = (
                f"[{icon}] [{entry.get('timestamp', '')[:19]}]  "
                f"claims={entry.get('total_claims', 0)}  "
                f"flagged={entry.get('flagged_count', 0)}  "
                f"blocked={entry.get('blocked_count', 0)}  "
                f"conf={conf:.2f}  "
                f"{entry.get('processing_time_ms', 0):.0f}ms"
                + ("  **BLOCKED**" if blocked else "")
            )
            with st.expander(label, expanded=False):
                st.json(entry, expanded=False)

    if auto_refresh:
        import time  # noqa: PLC0415
        time.sleep(5)
        st.rerun()
