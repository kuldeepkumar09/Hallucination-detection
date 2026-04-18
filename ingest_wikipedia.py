#!/usr/bin/env python3
"""
Wikipedia Ingestion CLI

Fetch Wikipedia articles and add them to the knowledge base.

Usage:
  python ingest_wikipedia.py "Albert Einstein"
  python ingest_wikipedia.py "GDPR" "COVID-19 vaccine" "Machine learning"
  python ingest_wikipedia.py --list-topics
"""
import argparse
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUGGESTED_TOPICS = [
    "Albert Einstein",
    "General Data Protection Regulation",
    "COVID-19 vaccine",
    "Machine learning",
    "Penicillin",
    "World Health Organization",
    "Climate change",
    "Artificial intelligence",
    "Python (programming language)",
    "World War II",
]


def main():
    parser = argparse.ArgumentParser(description="Ingest Wikipedia articles into the knowledge base")
    parser.add_argument("topics", nargs="*", help="Wikipedia page titles to ingest")
    parser.add_argument("--list-topics", action="store_true", help="Show suggested topics")
    parser.add_argument("--language", default="en", help="Wikipedia language code (default: en)")
    args = parser.parse_args()

    if args.list_topics:
        print("\nSuggested topics to ingest:")
        for t in SUGGESTED_TOPICS:
            print(f"  - {t}")
        print(f"\nUsage: python ingest_wikipedia.py \"{'\" \"'.join(SUGGESTED_TOPICS[:3])}\"")
        return

    if not args.topics:
        print("Usage: python ingest_wikipedia.py \"Topic Name\" [\"Topic 2\" ...]")
        print("       python ingest_wikipedia.py --list-topics")
        sys.exit(1)

    from hallucination_middleware import ingest_from_wikipedia

    print(f"\nIngesting {len(args.topics)} Wikipedia article(s)...\n")
    total_chunks = 0

    for topic in args.topics:
        print(f"  Fetching: '{topic}'...", end=" ", flush=True)
        chunks = ingest_from_wikipedia(topic, language=args.language)
        if chunks > 0:
            print(f"OK  (+{chunks} chunks)")
            total_chunks += chunks
        else:
            print("NOT FOUND")

    print(f"\nDone. Total chunks added: {total_chunks}")
    print("Run python demo.py or python run_proxy.py to use updated knowledge base.\n")


if __name__ == "__main__":
    main()
