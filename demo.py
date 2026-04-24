#!/usr/bin/env python3
"""
Hallucination Detection Middleware -- standalone demo.

Ingests a curated knowledge base of authoritative documents, then runs
four test LLM outputs through the pipeline.  Each output contains a mix
of correct facts, subtle errors, and outright hallucinations.

Usage:
  python demo.py               # run full demo
  python demo.py --clear-kb    # rebuild KB from scratch first
"""
import argparse
import asyncio
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(highlight=False)

# ---------------------------------------------------------------------------
# Sample authoritative documents
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {
        "source": "WHO Global Health Statistics 2023",
        "text": """
World Health Organization Global Health Statistics 2023:
- Global life expectancy at birth: 73.4 years (2022)
- Diabetes affects approximately 422 million people worldwide (not 500 million)
- Cardiovascular diseases cause 17.9 million deaths per year globally
- COVID-19 pandemic began in December 2019 in Wuhan, China
- The first COVID-19 vaccine authorized for emergency use was Pfizer-BioNTech in December 2020
- Aspirin (acetylsalicylic acid) is an analgesic, antipyretic, and anti-inflammatory drug
- Ibuprofen should NOT be used in the third trimester of pregnancy due to risk of premature
  closure of the ductus arteriosus
- Penicillin was discovered by Alexander Fleming in 1928
- Global maternal mortality rate: 223 per 100,000 live births (2020)
""",
    },
    {
        "source": "World Geography Reference 2024",
        "text": """
World Geography and Demographics 2024:
- World population as of 2024: approximately 8.1 billion people
- Paris is the capital and largest city of France
- France has a population of approximately 68 million people (2023)
- The Amazon River is the largest river by discharge volume in the world
- Mount Everest is the highest mountain above sea level at 8,848.86 metres
- The Great Wall of China was built over many centuries, primarily during the Ming Dynasty (1368-1644)
- The United States of America has 50 states
- The Nile River is generally considered the longest river at approximately 6,650 km
- Brazil is the largest country in South America by both area and population
""",
    },
    {
        "source": "EU GDPR Official Summary",
        "text": """
European Union General Data Protection Regulation (GDPR) Key Facts:
- GDPR entered into force on 25 May 2018 (not June 2019)
- Applies to all organisations processing personal data of EU residents
- Maximum fine: 20 million EUR OR 4% of global annual turnover, whichever is higher
  (NOT 10 million EUR or 2%)
- Data subjects have the right to erasure ("right to be forgotten")
- Data breaches must be reported to supervisory authority within 72 hours (not 24 hours)
- Data Protection Officer (DPO) required only in certain cases, not all companies
- Personal data must not be transferred to countries without adequate protection
- Lawful bases for processing: consent, contract, legal obligation, vital interests,
  public task, legitimate interests
""",
    },
    {
        "source": "Physics and Science Reference",
        "text": """
Physics Fundamental Constants and Scientific History:
- Speed of light in vacuum: 299,792,458 m/s (approximately 3x10^8 m/s)
- Albert Einstein was born on 14 March 1879 in Ulm, Germany (not Berlin)
- Einstein published Special Theory of Relativity in 1905 (not 1912)
- Einstein published General Theory of Relativity in 1915
- Einstein died on 18 April 1955 in Princeton, New Jersey
- Einstein won the 1921 Nobel Prize in Physics for the photoelectric effect
  (NOT for the Theory of Relativity)
- The electron was discovered by J.J. Thomson in 1897
- Newton's First Law: An object in motion stays in motion unless acted upon by external force
- Gravitational constant G = 6.674x10^-11 N*m^2/kg^2
""",
    },
    {
        "source": "Technology History Reference",
        "text": """
Technology and Computing History:
- The World Wide Web was invented by Tim Berners-Lee in 1989
- The first iPhone was released by Apple on 29 June 2007
- Microsoft was founded by Bill Gates and Paul Allen in 1975
- Apple Inc. was co-founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976
- Google was founded by Larry Page and Sergey Brin in 1998
- The Linux kernel was created by Linus Torvalds in 1991
- Python programming language was created by Guido van Rossum, first released in 1991
- Java was developed by James Gosling at Sun Microsystems, released in 1995
""",
    },
]

# ---------------------------------------------------------------------------
# Test cases -- each contains verified facts, partial errors, and hallucinations
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "Medical Information",
        "description": "Mix of correct and dangerous medical misinformation",
        "text": (
            "Penicillin, discovered by Alexander Fleming in 1928, revolutionised medicine. "
            "According to the WHO, diabetes currently affects approximately 500 million people "
            "worldwide. Ibuprofen is safe to use throughout all trimesters of pregnancy and is "
            "often recommended for pain management during labour. The first COVID-19 vaccine "
            "authorised for emergency use was the Pfizer-BioNTech vaccine in December 2020."
        ),
    },
    {
        "name": "Legal & Regulatory Claims",
        "description": "GDPR facts with several deliberate errors",
        "text": (
            "The EU GDPR, which came into force on 1 June 2019, is a landmark data protection "
            "regulation. Under GDPR, data breaches must be reported to supervisory authorities "
            "within 24 hours of discovery. The maximum penalty is 10 million EUR or 2% of global "
            "annual turnover. All companies processing EU personal data must appoint a Data "
            "Protection Officer without exception."
        ),
    },
    {
        "name": "Science & History Facts",
        "description": "Physics history with subtle errors that models commonly hallucinate",
        "text": (
            "Albert Einstein was born in Berlin, Germany on 14 March 1879. He published his "
            "Special Theory of Relativity in 1912. The speed of light is approximately 250,000 "
            "kilometres per second. Einstein won the Nobel Prize in Physics in 1921 for his "
            "Theory of Relativity. The electron was discovered by J.J. Thomson in 1897."
        ),
    },
    {
        "name": "Technology History",
        "description": "Well-documented tech history -- mostly verifiable",
        "text": (
            "The World Wide Web was invented by Tim Berners-Lee in 1989, making information "
            "globally accessible. Google was founded by Larry Page and Sergey Brin in 1998. "
            "Apple was co-founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976. "
            "The first iPhone launched on 29 June 2007 with a revolutionary multi-touch screen. "
            "Python, created by Guido van Rossum, was first released in 1991."
        ),
    },
]

# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------


async def run_demo(clear_kb: bool = False) -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Hallucination Detection Middleware v3[/bold cyan]\n"
            "[dim]Real-time verification: ChromaDB + Web-RAG + Domain Thresholds + Self-Correction[/dim]",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )

    from hallucination_middleware import HallucinationDetectionPipeline, KnowledgeBase  # noqa: PLC0415
    from hallucination_middleware.config import get_settings
    cfg = get_settings()
    if cfg.llm_provider == "ollama":
        console.print(f"  [dim]LLM: Ollama ({cfg.extractor_model}) at {cfg.ollama_base_url}[/dim]")
    elif cfg.llm_provider == "anthropic" and not cfg.anthropic_api_key:
        console.print("[bold red]Error:[/bold red] LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    # -- Set up knowledge base --
    console.print("\n[bold][1] Knowledge Base Setup[/bold]")
    kb = KnowledgeBase()

    if clear_kb:
        console.print("  [yellow]Clearing existing KB...[/yellow]")
        kb.clear()

    if kb.stats()["total_chunks"] == 0:
        console.print("  Ingesting sample authoritative documents...")
        for doc in SAMPLE_DOCS:
            chunks = kb.ingest_text(doc["text"], source=doc["source"])
            console.print(f"  [green]OK[/green] {doc['source']}  ({chunks} chunks)")
    else:
        console.print(
            f"  [green]OK[/green] KB already loaded - {kb.stats()['total_chunks']} chunks"
        )

    # -- Initialise pipeline --
    console.print("\n[bold][2] Pipeline Initialisation[/bold]")
    pipeline = HallucinationDetectionPipeline()
    console.print("  [green]OK[/green] Pipeline ready")

    # -- Run test cases --
    console.print("\n[bold][3] Processing Test Cases[/bold]")

    for idx, tc in enumerate(TEST_CASES, 1):
        console.print(f"\n{'-'*72}")
        console.print(f"[bold cyan]Test {idx}/{len(TEST_CASES)}: {tc['name']}[/bold cyan]")
        console.print(f"[dim]{tc['description']}[/dim]\n")

        console.print(
            Panel(tc["text"].strip(), title="[yellow]LLM Output[/yellow]", border_style="yellow dim")
        )

        with console.status("[bold green]Running detection...[/bold green]"):
            audit = await pipeline.process(tc["text"], model="demo")

        # Claims table
        if audit.claims:
            tbl = Table(
                title="Claims Analysis",
                box=box.SIMPLE_HEAD,
                show_header=True,
                header_style="bold white",
                expand=False,
            )
            tbl.add_column("Claim", max_width=42, overflow="fold")
            tbl.add_column("Type", width=11)
            tbl.add_column("Stakes", width=9)
            tbl.add_column("Status", width=20)
            tbl.add_column("Conf", width=5, justify="right")
            tbl.add_column("Action", width=8)

            STATUS_STYLE = {
                "verified": "green",
                "contradicted": "bold red",
                "unverifiable": "yellow",
                "partially_supported": "dark_orange",
            }
            ACTION_STYLE = {
                "block": "bold red",
                "flag": "yellow",
                "annotate": "green",
                "pass": "dim",
            }

            for d in audit.claims:
                vc = d.verified_claim
                c = vc.claim
                preview = c.text[:42] + ("..." if len(c.text) > 42 else "")
                ss = STATUS_STYLE.get(vc.status.value, "white")
                as_ = ACTION_STYLE.get(d.action.value, "white")
                tbl.add_row(
                    preview,
                    c.claim_type.value,
                    c.stakes.value,
                    f"[{ss}]{vc.status.value}[/{ss}]",
                    f"{vc.confidence:.2f}",
                    f"[{as_}]{d.action.value.upper()}[/{as_}]",
                )
            console.print(tbl)

        # Before/after self-correction side-by-side panel
        if audit.corrected_text and audit.corrected_text.strip() != tc["text"].strip():
            console.print(
                Panel(
                    f"[bold red]ORIGINAL (with hallucinations):[/bold red]\n"
                    f"[dim]{tc['text'].strip()}[/dim]\n\n"
                    f"[bold green]CORRECTED (self-corrected):[/bold green]\n"
                    f"{audit.corrected_text.strip()}",
                    title="[cyan]Self-Correction — Before vs After[/cyan]",
                    border_style="cyan",
                    box=box.DOUBLE_EDGE,
                )
            )
        elif audit.annotated_text.strip() != tc["text"].strip():
            console.print(
                Panel(
                    audit.annotated_text,
                    title="[cyan]Annotated Response[/cyan]",
                    border_style="cyan dim",
                )
            )

        # Summary line
        blocked_icon = "[bold red]RESPONSE BLOCKED[/bold red]" if audit.response_blocked else ""
        console.print(
            f"  [dim]Claims: {audit.total_claims} total"
            f" | {audit.verified_count} verified"
            f" | {audit.flagged_count} flagged"
            f" | {audit.blocked_count} blocked"
            f" | Confidence: [bold]{audit.overall_confidence:.2f}[/bold]"
            f" | {audit.processing_time_ms:.0f}ms[/dim]  {blocked_icon}"
        )
        if audit.response_blocked:
            console.print(f"  [bold red]  Reason: {audit.block_reason}[/bold red]")

    # -- Session summary --
    console.print(f"\n{'-'*72}")
    console.print("[bold][4] Session Summary[/bold]\n")

    from hallucination_middleware import AuditTrail  # noqa: PLC0415
    trail = AuditTrail()
    s = trail.get_stats()

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="bold green", justify="right")
    for k, v in s.items():
        summary.add_row(k.replace("_", " ").title(), str(v))
    console.print(summary)

    console.print(f"\n[dim]Audit log saved to: {trail._path}[/dim]")
    console.print(
        "\n[bold green]Demo complete.[/bold green] "
        "Run [cyan]python run_proxy.py[/cyan] to start the HTTP proxy.\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hallucination Detection Demo")
    parser.add_argument(
        "--clear-kb",
        action="store_true",
        help="Clear and rebuild the knowledge base before running.",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(clear_kb=args.clear_kb))
