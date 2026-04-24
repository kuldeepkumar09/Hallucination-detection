#!/usr/bin/env python3
"""
Ingest a curated set of foundational Wikipedia articles into the knowledge base.

Run once to bootstrap the KB with high-quality authoritative content across
medicine, law, finance, history, science, and technology domains.

Usage:
    python ingest_starter_kb.py
    python ingest_starter_kb.py --mode summary   # faster, less content
    python ingest_starter_kb.py --topics "Albert Einstein" "DNA"  # specific topics
    python ingest_starter_kb.py --list           # show all topics without ingesting
"""
import argparse
import logging
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated topic list — covers common claim domains for hallucination detection
# ---------------------------------------------------------------------------

STARTER_TOPICS = {
    "Medical": [
        "COVID-19 pandemic",
        "Vaccination",
        "Diabetes mellitus",
        "Penicillin",
        "Cancer",
        "Hypertension",
        "Alzheimer's disease",
        "HIV/AIDS",
        "Malaria",
        "Influenza",
    ],
    "Legal & Regulatory": [
        "United States Constitution",
        "General Data Protection Regulation",
        "United Nations",
        "European Union",
        "Geneva Conventions",
        "Universal Declaration of Human Rights",
    ],
    "Financial": [
        "Inflation",
        "Stock market",
        "Federal Reserve",
        "Cryptocurrency",
        "Great Depression",
        "Gross domestic product",
        "Interest rate",
    ],
    "History": [
        "World War II",
        "World War I",
        "French Revolution",
        "Industrial Revolution",
        "Cold War",
        "American Civil War",
        "Moon landing",
    ],
    "Science": [
        "Albert Einstein",
        "DNA",
        "Climate change",
        "Quantum mechanics",
        "Evolution",
        "Big Bang",
        "Periodic table",
        "Black hole",
    ],
    "Technology": [
        "Artificial intelligence",
        "Internet",
        "Python (programming language)",
        "Machine learning",
        "Semiconductor",
        "Space exploration",
    ],
    "Geography & World": [
        "United States",
        "India",
        "China",
        "European Union",
        "Amazon River",
        "Himalayas",
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Ingest Wikipedia starter KB")
    parser.add_argument("--mode", choices=["full", "summary"], default="full",
                        help="full = entire article, summary = intro paragraph only")
    parser.add_argument("--topics", nargs="+", help="Specific topics to ingest")
    parser.add_argument("--list", action="store_true", help="List all topics without ingesting")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip topics already in KB (default: True)")
    args = parser.parse_args()

    if args.list:
        print("\nStarterKB topics:")
        for category, topics in STARTER_TOPICS.items():
            print(f"\n  {category}:")
            for t in topics:
                print(f"    - {t}")
        print(f"\nTotal: {sum(len(v) for v in STARTER_TOPICS.values())} topics")
        return

    from hallucination_middleware.knowledge_base import KnowledgeBase
    from hallucination_middleware.wikipedia_ingest import ingest_from_wikipedia

    kb = KnowledgeBase()
    current_chunks = kb._col.count()
    print(f"\nCurrent KB: {current_chunks:,} chunks")

    # Determine topics to ingest
    if args.topics:
        topics_to_ingest = [(t, "Custom") for t in args.topics]
    else:
        topics_to_ingest = [
            (topic, category)
            for category, topics in STARTER_TOPICS.items()
            for topic in topics
        ]

    # Check which are already ingested
    if args.skip_existing and not args.topics:
        existing_sources = set()
        try:
            docs = kb.list_documents()
            for d in docs:
                src = d.get("source", "")
                if src.startswith("wikipedia:"):
                    existing_sources.add(src.replace("wikipedia:", "").split("#")[0].lower())
        except Exception:
            pass

        topics_to_ingest = [
            (t, c) for t, c in topics_to_ingest
            if t.lower() not in existing_sources
        ]

        if not topics_to_ingest:
            print("All topics already in KB. Use --skip-existing=false to re-ingest.")
            return

    total = len(topics_to_ingest)
    print(f"Ingesting {total} topics in '{args.mode}' mode...\n")

    results = {}
    t0 = time.time()

    for i, (topic, category) in enumerate(topics_to_ingest, 1):
        print(f"[{i}/{total}] {category}: {topic}...", end=" ", flush=True)
        try:
            chunks = ingest_from_wikipedia(topic, language="en", kb=kb, mode=args.mode)
            results[topic] = chunks
            if chunks > 0:
                print(f"{chunks} chunks added")
            else:
                print("not found / empty")
        except Exception as exc:
            print(f"ERROR: {exc}")
            results[topic] = 0

    elapsed = time.time() - t0
    added = sum(results.values())
    new_total = kb._col.count()

    print(f"\n{'='*50}")
    print(f"Done in {elapsed:.0f}s")
    print(f"Topics processed : {total}")
    print(f"Chunks added     : {added:,}")
    print(f"KB total chunks  : {new_total:,}")
    print(f"{'='*50}")

    failed = [t for t, c in results.items() if c == 0]
    if failed:
        print(f"\nFailed/empty ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()
