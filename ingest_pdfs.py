#!/usr/bin/env python3
"""
Direct PDF ingestion script — ingests all PDFs from yourfile.txt/ folder.
Run: python ingest_pdfs.py
"""
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from hallucination_middleware import KnowledgeBase

DATA_DIR = Path("yourfile.txt")

def main():
    if not DATA_DIR.exists():
        print(f"ERROR: Directory '{DATA_DIR}' not found.")
        sys.exit(1)

    pdfs = list(DATA_DIR.glob("**/*.pdf"))
    print(f"Found {len(pdfs)} PDF file(s) in '{DATA_DIR}/'")
    print()

    kb = KnowledgeBase()
    print(f"KB currently has {kb.stats()['total_chunks']} chunks\n")

    total_chunks = 0
    errors = []

    for i, fp in enumerate(sorted(pdfs), 1):
        try:
            chunks = kb.ingest_file(str(fp))
            total_chunks += chunks
            print(f"  [{i:03d}/{len(pdfs)}] OK  {fp.name}  ({chunks} chunks)")
        except Exception as exc:
            print(f"  [{i:03d}/{len(pdfs)}] ERR {fp.name}: {exc}")
            errors.append(str(fp))

    print()
    print(f"Done.")
    print(f"  Added chunks : {total_chunks}")
    print(f"  Errors       : {len(errors)}")
    print(f"  KB total     : {kb.stats()['total_chunks']}")

    if errors:
        print("\nFiles with errors:")
        for e in errors:
            print(f"  {e}")

if __name__ == "__main__":
    main()
