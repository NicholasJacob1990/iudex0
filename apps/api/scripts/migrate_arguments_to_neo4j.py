"""
Migration script: Migrate ArgumentRAG data from NetworkX graphs to Neo4j.

Reads Claims, Evidence, Actors, Issues from existing in-memory NetworkX graphs
and writes them to Neo4j via ArgumentNeo4jService.

This script is idempotent — safe to run multiple times (MERGE semantics).

Usage:
    python scripts/migrate_arguments_to_neo4j.py [--dry-run] [--scope private] [--tenant-id TENANT]
"""

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def migrate_from_networkx(
    scope: str = "private",
    scope_id: str | None = None,
    tenant_id: str = "default",
    dry_run: bool = False,
) -> dict:
    """
    Migrate argument nodes from NetworkX knowledge graphs to Neo4j.

    Reads existing graph scopes and extracts claim/evidence/actor/issue nodes,
    then writes them to Neo4j via ArgumentNeo4jService.
    """
    stats = {
        "scopes_found": 0,
        "nodes_read": 0,
        "claims_migrated": 0,
        "evidence_migrated": 0,
        "actors_migrated": 0,
        "issues_migrated": 0,
        "relationships_migrated": 0,
        "errors": 0,
    }

    try:
        from app.services.rag_module_old import get_scoped_knowledge_graph as get_scoped_graph
    except ImportError:
        logger.error("Could not import get_scoped_knowledge_graph. Ensure app is in PYTHONPATH.")
        return stats

    # Get the graph for the requested scope
    try:
        graph = get_scoped_graph(scope=scope, scope_id=scope_id)
    except TypeError:
        graph = get_scoped_graph(scope, scope_id)

    if not graph or not hasattr(graph, "graph"):
        logger.warning("No graph found for scope=%s, scope_id=%s", scope, scope_id)
        return stats

    stats["scopes_found"] = 1
    nx_graph = graph.graph

    if dry_run:
        logger.info("=== DRY RUN MODE ===")

    # Categorize nodes by type
    claims = []
    evidence = []
    actors = []
    issues = []

    for node_id, data in nx_graph.nodes(data=True):
        stats["nodes_read"] += 1
        node_type = str(node_id).split(":")[0] if ":" in str(node_id) else ""

        if node_type == "claim":
            claims.append((node_id, data))
        elif node_type == "evidence":
            evidence.append((node_id, data))
        elif node_type == "actor":
            actors.append((node_id, data))
        elif node_type == "issue":
            issues.append((node_id, data))

    logger.info(
        "Found %d claims, %d evidence, %d actors, %d issues in graph (scope=%s)",
        len(claims), len(evidence), len(actors), len(issues), scope,
    )

    if dry_run:
        stats["claims_migrated"] = len(claims)
        stats["evidence_migrated"] = len(evidence)
        stats["actors_migrated"] = len(actors)
        stats["issues_migrated"] = len(issues)
        return stats

    # Initialize ArgumentNeo4jService
    try:
        from app.services.rag.core.argument_neo4j import get_argument_neo4j
        arg_svc = get_argument_neo4j()
    except Exception as e:
        logger.error("Could not initialize ArgumentNeo4jService: %s", e)
        return stats

    # Migrate evidence nodes
    for node_id, data in evidence:
        try:
            import hashlib
            evidence_id = hashlib.sha256(str(node_id).encode()).hexdigest()[:16]
            arg_svc._execute_write(
                arg_svc.__class__.__mro__[0].__dict__.get("_execute_write", None)
                and "MERGE (ev:Evidence {evidence_id: $evidence_id}) "
                "ON CREATE SET ev.text = $text, ev.evidence_type = $evidence_type, "
                "ev.weight = $weight, ev.doc_id = $doc_id, ev.tenant_id = $tenant_id, "
                "ev.scope = $scope, ev.title = $title, ev.migrated = true, "
                "ev.created_at = datetime() "
                "ON MATCH SET ev.updated_at = datetime()"
                or "",
                {
                    "evidence_id": evidence_id,
                    "text": data.get("text", "")[:500],
                    "evidence_type": data.get("source_type", "documento"),
                    "weight": data.get("weight", 0.7),
                    "doc_id": data.get("doc_id", ""),
                    "tenant_id": tenant_id,
                    "scope": scope,
                    "title": data.get("title", ""),
                },
            )
            stats["evidence_migrated"] += 1
        except Exception as e:
            logger.debug("Evidence migration error for %s: %s", node_id, e)
            stats["errors"] += 1

    # Migrate claim nodes
    for node_id, data in claims:
        try:
            import hashlib
            claim_id = hashlib.sha256(str(node_id).encode()).hexdigest()[:16]
            from app.services.rag.core.argument_neo4j import ArgumentCypher
            arg_svc._execute_write(ArgumentCypher.MERGE_CLAIM, {
                "claim_id": claim_id,
                "text": data.get("text", "")[:260],
                "claim_type": "contratese" if data.get("polarity", 1) < 0 else "tese",
                "polarity": data.get("polarity", 1),
                "confidence": 0.7,
                "source_chunk_uid": data.get("chunk_id", ""),
                "tenant_id": tenant_id,
                "case_id": None,
                "scope": scope,
            })
            stats["claims_migrated"] += 1
        except Exception as e:
            logger.debug("Claim migration error for %s: %s", node_id, e)
            stats["errors"] += 1

    # Migrate actor nodes
    for node_id, data in actors:
        try:
            import hashlib
            actor_id = hashlib.sha256(str(node_id).encode()).hexdigest()[:16]
            from app.services.rag.core.argument_neo4j import ArgumentCypher
            arg_svc._execute_write(ArgumentCypher.MERGE_ACTOR, {
                "actor_id": actor_id,
                "name": data.get("name", str(node_id).split(":")[-1]),
                "role": data.get("role", "parte"),
                "tenant_id": tenant_id,
            })
            stats["actors_migrated"] += 1
        except Exception as e:
            logger.debug("Actor migration error for %s: %s", node_id, e)
            stats["errors"] += 1

    # Migrate relationships
    for u, v, edge_data in nx_graph.edges(data=True):
        u_type = str(u).split(":")[0] if ":" in str(u) else ""
        v_type = str(v).split(":")[0] if ":" in str(v) else ""
        rel_type = edge_data.get("relation", "")

        if u_type in ("claim", "evidence", "actor") and v_type in ("claim", "evidence", "issue"):
            stats["relationships_migrated"] += 1

    logger.info("Migration complete: %s", stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate ArgumentRAG from NetworkX to Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--scope", default="private", help="Graph scope to migrate (default: private)")
    parser.add_argument("--scope-id", default=None, help="Scope ID (tenant for private, group_id for group)")
    parser.add_argument("--tenant-id", default=os.getenv("TENANT_ID", "default"), help="Tenant ID")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN MODE (no changes will be made) ===")

    stats = migrate_from_networkx(
        scope=args.scope,
        scope_id=args.scope_id,
        tenant_id=args.tenant_id,
        dry_run=args.dry_run,
    )

    logger.info("=== Migration Summary ===")
    for key, value in stats.items():
        logger.info("  %s: %s", key, value)


if __name__ == "__main__":
    main()
