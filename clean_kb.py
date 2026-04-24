#!/usr/bin/env python3
"""
Clean Knowledge Base — Remove all non-Wikipedia documents from ChromaDB.

This script deletes every document whose source does NOT start with "wikipedia:",
leaving only curated Wikipedia content in the knowledge base.
"""
import sys

from hallucination_middleware.knowledge_base import KnowledgeBase


def clean_kb():
    print("Connecting to Knowledge Base...")
    kb = KnowledgeBase()

    docs = kb.list_documents()
    total_docs = len(docs)
    print(f"Found {total_docs} documents in KB")

    # Separate Wikipedia vs non-Wikipedia documents
    wiki_docs = [d for d in docs if d["source"].startswith("wikipedia:")]
    junk_docs = [d for d in docs if not d["source"].startswith("wikipedia:")]

    print(f"\n  Wikipedia documents: {len(wiki_docs)}")
    print(f"  Non-Wikipedia documents (to delete): {len(junk_docs)}")

    if not junk_docs:
        print("\nNo junk documents found. KB is clean!")
        return

    print("\nDeleting non-Wikipedia documents...")
    total_deleted = 0
    for doc in junk_docs:
        doc_id = doc["doc_id"]
        source = doc["source"]
        chunk_count = doc["chunk_count"]
        deleted = kb.delete_document(doc_id)
        total_deleted += deleted
        print(f"  Deleted '{source}' — {deleted} chunks removed")

    print(f"\nTotal chunks deleted: {total_deleted}")

    # Print final stats
    stats = kb.stats()
    print("\n=== Final KB Stats ===")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Collection: {stats['collection']}")
    print(f"  BM25 indexed: {stats['bm25_indexed']}")

    # Verify only Wikipedia docs remain
    remaining_docs = kb.list_documents()
    wiki_remaining = [d for d in remaining_docs if d["source"].startswith("wikipedia:")]
    non_wiki_remaining = [d for d in remaining_docs if not d["source"].startswith("wikipedia:")]

    print(f"\n=== Verification ===")
    print(f"  Remaining documents: {len(remaining_docs)}")
    print(f"  Wikipedia documents: {len(wiki_remaining)}")
    print(f"  Non-Wikipedia documents: {len(non_wiki_remaining)}")

    if non_wiki_remaining:
        print("\nWARNING: Some non-Wikipedia documents still remain:")
        for d in non_wiki_remaining:
            print(f"  - {d['source']} ({d['chunk_count']} chunks)")
    else:
        print("\n✓ KB cleanup complete — only Wikipedia content remains!")


if __name__ == "__main__":
    clean_kb()