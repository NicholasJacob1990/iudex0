#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from typing import Dict


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return val if val is not None else default


def _redact_uri(uri: str) -> str:
    # Avoid leaking credentials if present in URI; keep scheme + host.
    # neo4j driver URIs typically don't embed credentials, but be defensive.
    if "@" in uri:
        return uri.split("@", 1)[-1]
    return uri


def main() -> int:
    try:
        from neo4j import GraphDatabase
    except Exception as e:
        print(f"neo4j driver not installed: {e}", file=sys.stderr)
        return 2

    uri = _env("NEO4J_URI", "bolt://localhost:7687")
    user = _env("NEO4J_USER", _env("NEO4J_USERNAME", "neo4j"))
    password = _env("NEO4J_PASSWORD", "")
    database = _env("NEO4J_DATABASE", "neo4j")

    if not password:
        print("Missing NEO4J_PASSWORD (set it in env).", file=sys.stderr)
        return 2

    from app.services.rag.core.graph_hybrid import ensure_neo4j_schema, migrate_hybrid_labels

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            ensure_neo4j_schema(session, hybrid=True)
            results: Dict[str, int] = migrate_hybrid_labels(session)

        print(f"Neo4j hybrid migration complete (db={database}, uri={_redact_uri(uri)}).")
        for label, count in sorted(results.items()):
            print(f"- {label}: {count} nodes updated")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())

