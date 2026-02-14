"""CLI entry point for neo4j-rag."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="neo4j-rag",
    help="Standalone Neo4j RAG for legal study materials.",
)
console = Console()


@app.command()
def setup(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Create required Neo4j indexes and constraints."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from neo4j import GraphDatabase
    from .config import settings
    from .pipeline import ensure_indexes

    console.print("[bold]Creating Neo4j indexes...[/bold]")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            ensure_indexes(session)
    finally:
        driver.close()
    console.print("[green]Indexes created successfully.[/green]")


@app.command()
def ingest(
    dir: str = typer.Option(..., "--dir", "-d", help="Directory with PDF/DOCX files"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Files per batch"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM for contextual prefixes"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Ingest documents into Neo4j."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .pipeline import ingest_directory

    console.print(f"[bold]Ingesting from:[/bold] {dir}")
    stats = ingest_directory(dir, batch_size=batch_size, use_contextual_llm=use_llm)

    table = Table(title="Ingest Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row("Documents", str(stats.documents_created))
    table.add_row("Chunks", str(stats.chunks_created))
    table.add_row("Entities", str(stats.entities_extracted))
    table.add_row("MENTIONS edges", str(stats.mentions_created))
    table.add_row("NEXT edges", str(stats.next_edges_created))
    table.add_row("PARTE_DE edges", str(stats.pertence_a_created))
    table.add_row("SUBDISPOSITIVO_DE edges", str(stats.subdispositivo_de_created))
    table.add_row("Errors", str(len(stats.errors)))
    console.print(table)

    if stats.errors:
        console.print(f"\n[bold red]Errors ({len(stats.errors)}):[/bold red]")
        for err in stats.errors[:10]:
            console.print(f"  - {err}")
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_n: int = typer.Option(5, "--top", "-n", help="Number of results"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Search the knowledge graph."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .pipeline import search as do_search

    console.print(f"[bold]Query:[/bold] {query}\n")
    result = do_search(query, top_n=top_n)

    console.print(f"[dim]Total candidates: {result.total_candidates}[/dim]\n")

    for i, r in enumerate(result.results, 1):
        console.print(f"[bold cyan]#{i}[/bold cyan] (score: {r.score:.4f})")
        text_preview = r.text[:300] + "..." if len(r.text) > 300 else r.text
        console.print(f"  {text_preview}\n")


@app.command()
def eval(
    dataset: str = typer.Option(..., "--dataset", "-d", help="Path to golden QA JSONL"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Evaluate retrieval quality against a golden dataset."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .pipeline import search as do_search

    path = Path(dataset)
    if not path.exists():
        console.print(f"[red]Dataset not found: {dataset}[/red]")
        raise typer.Exit(1)

    questions = []
    for line in path.read_text().strip().split("\n"):
        if line.strip():
            questions.append(json.loads(line))

    console.print(f"[bold]Evaluating {len(questions)} questions...[/bold]\n")

    total_hits = 0
    for q in questions:
        query = q["question"]
        expected = q.get("expected_entities", [])
        result = do_search(query, top_n=5)

        # Check if any expected entity appears in results
        all_text = " ".join(r.text for r in result.results)
        hits = sum(1 for e in expected if e.lower() in all_text.lower())
        hit_rate = hits / len(expected) if expected else 0
        total_hits += hit_rate

        status = "[green]OK[/green]" if hit_rate > 0.5 else "[red]MISS[/red]"
        console.print(f"  {status} {query[:60]}... ({hits}/{len(expected)})")

    avg = total_hits / len(questions) if questions else 0
    console.print(f"\n[bold]Average hit rate: {avg:.2%}[/bold]")


if __name__ == "__main__":
    app()
