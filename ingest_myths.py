"""
Ingest myth-busting fact pairs into the knowledge base.

Usage:
    python ingest_myths.py

This adds authoritative corrections for common misconceptions so the
hallucination detector can CONTRADICT false claims instead of returning
'unverifiable'.
"""
import sys
import time

from myth_facts import MYTH_FACTS
from hallucination_middleware.knowledge_base import KnowledgeBase


def main() -> None:
    print("Loading knowledge base...")
    kb = KnowledgeBase()
    before = kb._col.count()
    print(f"Current KB size: {before} chunks")
    print()

    total_chunks = 0
    for i, entry in enumerate(MYTH_FACTS, 1):
        source = entry["source"]
        text = entry["fact"]
        category = entry.get("category", "GENERAL")
        chunks = kb.ingest_text(text, source=source)
        total_chunks += chunks
        print(f"[{i:2d}/{len(MYTH_FACTS)}] {source} ({category}): {chunks} chunk(s)")
        time.sleep(0.05)  # brief pause between ingestions

    after = kb._col.count()
    print()
    print(f"Done — added {total_chunks} chunks ({after - before} net new)")
    print(f"Total KB size: {after} chunks")
    print()
    print("The KB now contains authoritative myth-busting content.")
    print("Re-run the demo to see improved contradiction detection.")


if __name__ == "__main__":
    main()
