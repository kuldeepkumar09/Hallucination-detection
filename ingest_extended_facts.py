"""
Ingest extended authoritative facts into the knowledge base.
Usage: python ingest_extended_facts.py
"""
import sys, time
from extended_facts import EXTENDED_FACTS
from hallucination_middleware.knowledge_base import KnowledgeBase


def main() -> None:
    print("Loading knowledge base…")
    kb = KnowledgeBase()
    before = kb._col.count()
    print(f"Current KB size: {before} chunks\n")

    total_chunks = 0
    by_category: dict = {}
    for i, entry in enumerate(EXTENDED_FACTS, 1):
        source = entry["source"]
        text = entry["fact"]
        category = entry.get("category", "GENERAL")
        chunks = kb.ingest_text(text, source=source)
        total_chunks += chunks
        by_category.setdefault(category, 0)
        by_category[category] += chunks
        print(f"[{i:2d}/{len(EXTENDED_FACTS)}] {source} ({category}): {chunks} chunk(s)")
        time.sleep(0.03)

    after = kb._col.count()
    print(f"\nDone — added {total_chunks} chunks ({after - before} net new)")
    print(f"Total KB size: {after} chunks")
    print("\nBy category:")
    for cat, n in sorted(by_category.items()):
        print(f"  {cat}: {n} chunks")


if __name__ == "__main__":
    main()
