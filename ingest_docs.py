#!/usr/bin/env python3
"""
CLI for managing the hallucination detection knowledge base.

Commands:
  ingest <path ...>        Ingest files or directories (.txt, .pdf)
  url <url ...>            Fetch URLs and ingest their text
  text <text>              Ingest raw text directly
  list-docs                List all ingested documents
  delete-doc <doc_id>      Remove a document by ID
  stats                    Show KB + audit statistics
  clear                    Delete all documents (destructive)

Examples:
  python ingest_docs.py ingest ./docs/
  python ingest_docs.py ingest report.pdf notes.txt
  python ingest_docs.py url https://www.who.int/news-room/fact-sheets/detail/diabetes
  python ingest_docs.py text "Paris is the capital of France." --source geography
  python ingest_docs.py list-docs
  python ingest_docs.py delete-doc abc123def456
  python ingest_docs.py stats
  python ingest_docs.py clear --yes
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = typer.Typer(help="Manage the hallucination detection knowledge base.", add_completion=False)
console = Console()


def _kb():
    from hallucination_middleware import KnowledgeBase  # noqa: PLC0415
    return KnowledgeBase()


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@app.command()
def ingest(
    paths: list[str] = typer.Argument(..., help="Files or directories to ingest."),
    glob_pattern: str = typer.Option(
        "**/*.txt,**/*.pdf", "--glob", "-g",
        help="Comma-separated glob patterns for directory ingestion.",
    ),
) -> None:
    """Ingest .txt / .pdf files or directories into the knowledge base."""
    kb = _kb()
    total_chunks, errors = 0, []

    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            console.print(f"[red]Not found:[/red] {path_str}")
            errors.append(path_str)
            continue

        if p.is_dir():
            all_files: list[Path] = []
            for pattern in glob_pattern.split(","):
                all_files.extend(p.glob(pattern.strip()))
            console.print(f"[cyan]{p.name}/[/cyan] — {len(all_files)} file(s) found")
            for fp in all_files:
                try:
                    chunks = kb.ingest_file(str(fp))
                    total_chunks += chunks
                    console.print(f"  [green]OK[/green] {fp.name}: {chunks} chunks")
                except Exception as exc:  # noqa: BLE001
                    console.print(f"  [red]ERR[/red] {fp.name}: {exc}")
                    errors.append(str(fp))
        elif p.is_file():
            try:
                chunks = kb.ingest_file(str(p))
                total_chunks += chunks
                console.print(f"[green]OK[/green] {p.name}: {chunks} chunks")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]ERR[/red] {p.name}: {exc}")
                errors.append(str(p))

    color = "red" if errors else "green"
    console.print(
        f"\n[bold]Done.[/bold]  Added: [green]{total_chunks}[/green] chunks"
        f"  |  Errors: [{color}]{len(errors)}[/{color}]"
        f"  |  KB total: [cyan]{kb.stats()['total_chunks']}[/cyan]"
    )
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------------------
# url
# ---------------------------------------------------------------------------

@app.command()
def url(
    urls: list[str] = typer.Argument(..., help="URLs to fetch and ingest."),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source label override."),
) -> None:
    """Fetch URL(s) and ingest their text into the knowledge base."""
    kb = _kb()
    total_chunks, errors = 0, []

    for u in urls:
        try:
            chunks = asyncio.run(kb.ingest_url(u, source=source or u))
            total_chunks += chunks
            console.print(f"[green]OK[/green] {u[:80]}: {chunks} chunks")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]ERR[/red] {u[:80]}: {exc}")
            errors.append(u)

    color = "red" if errors else "green"
    console.print(
        f"\n[bold]Done.[/bold]  Added: [green]{total_chunks}[/green] chunks"
        f"  |  Errors: [{color}]{len(errors)}[/{color}]"
        f"  |  KB total: [cyan]{kb.stats()['total_chunks']}[/cyan]"
    )
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------

@app.command()
def text(
    content: str = typer.Argument(..., help="Text to ingest."),
    source: str = typer.Option("manual_input", "--source", "-s", help="Source label."),
) -> None:
    """Ingest raw text directly into the knowledge base."""
    kb = _kb()
    chunks = kb.ingest_text(content, source=source)
    console.print(f"[green]OK[/green] Ingested {chunks} chunk(s) from source '[cyan]{source}[/cyan]'")


# ---------------------------------------------------------------------------
# list-docs
# ---------------------------------------------------------------------------

@app.command(name="list-docs")
def list_docs() -> None:
    """List all ingested documents with chunk counts."""
    kb = _kb()
    docs = kb.list_documents()

    if not docs:
        console.print("[yellow]No documents in knowledge base.[/yellow]")
        return

    table = Table(title=f"Knowledge Base Documents ({len(docs)} total)", show_header=True, header_style="bold cyan")
    table.add_column("doc_id", style="dim", width=14)
    table.add_column("source", style="cyan")
    table.add_column("chunks", justify="right", style="green", width=8)

    for d in docs:
        table.add_row(d["doc_id"], d["source"], str(d["chunk_count"]))

    console.print(table)
    console.print(f"[dim]Total chunks: {kb.stats()['total_chunks']}[/dim]")


# ---------------------------------------------------------------------------
# delete-doc
# ---------------------------------------------------------------------------

@app.command(name="delete-doc")
def delete_doc(
    doc_id: str = typer.Argument(..., help="doc_id to delete (from list-docs)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove a specific document from the knowledge base by doc_id."""
    if not yes:
        typer.confirm(f"Delete all chunks for doc_id '{doc_id}'?", abort=True)
    kb = _kb()
    removed = kb.delete_document(doc_id)
    if removed:
        console.print(f"[green]OK[/green] Removed {removed} chunk(s) for doc_id '{doc_id}'")
    else:
        console.print(f"[yellow]No chunks found for doc_id '{doc_id}'[/yellow]")


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@app.command()
def stats() -> None:
    """Show knowledge base and audit trail statistics."""
    kb = _kb()
    kb_s = kb.stats()

    table = Table(title="Knowledge Base", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    for k, v in kb_s.items():
        table.add_row(k, str(v))
    console.print(table)

    # Per-source breakdown
    doc_stats = kb.get_document_stats()
    if doc_stats["by_source"]:
        console.print()
        src_table = Table(title="Chunks by Source", show_header=True, header_style="bold blue")
        src_table.add_column("Source", style="blue")
        src_table.add_column("Chunks", justify="right", style="green")
        for src, cnt in sorted(doc_stats["by_source"].items()):
            src_table.add_row(src[:60], str(cnt))
        console.print(src_table)

    try:
        from hallucination_middleware import AuditTrail  # noqa: PLC0415
        audit_s = AuditTrail().get_stats()
        if audit_s.get("total_requests", 0) > 0:
            console.print()
            a_table = Table(title="Audit Trail", show_header=True, header_style="bold magenta")
            a_table.add_column("Property", style="magenta")
            a_table.add_column("Value", style="green")
            for k, v in audit_s.items():
                a_table.add_row(k, str(v))
            console.print(a_table)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

@app.command()
def clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """[DESTRUCTIVE] Delete all documents from the knowledge base."""
    if not yes:
        typer.confirm("Delete ALL documents from the knowledge base?", abort=True)
    _kb().clear()
    console.print("[green]Knowledge base cleared.[/green]")


if __name__ == "__main__":
    app()
