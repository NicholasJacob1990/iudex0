"""
Migration script: Fix semantic entity labels and relationship types in Neo4j.

Changes:
1. Add :Entity label to all :SEMANTIC_ENTITY nodes (making them dual-labeled :Entity:SemanticEntity)
2. Rename :SEMANTICALLY_RELATED relationships to :RELATED_TO (with relation_subtype='semantic')
3. Rename :SEMANTIC_ENTITY label to :SemanticEntity (PascalCase, aligned with graph_hybrid.py)

This script is idempotent — safe to run multiple times.

Usage:
    python scripts/fix_semantic_relationships.py [--dry-run] [--neo4j-uri bolt://localhost:7687]
"""

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_driver(uri: str, user: str, password: str):
    """Create Neo4j driver."""
    from neo4j import GraphDatabase

    return GraphDatabase.driver(uri, auth=(user, password))


def migrate(driver, database: str, dry_run: bool = False) -> dict:
    """Run the migration steps. Returns stats dict."""
    stats = {
        "entities_relabeled": 0,
        "entities_pascalcase": 0,
        "relationships_migrated": 0,
        "old_relationships_deleted": 0,
    }

    with driver.session(database=database) as session:
        # Step 1: Add :Entity label to SEMANTIC_ENTITY nodes that don't have it
        logger.info("Step 1: Adding :Entity label to SEMANTIC_ENTITY nodes...")
        query_1 = """
        MATCH (n:SEMANTIC_ENTITY)
        WHERE NOT n:Entity
        RETURN count(n) as total
        """
        result = session.run(query_1).single()
        count = result["total"] if result else 0
        logger.info(f"  Found {count} SEMANTIC_ENTITY nodes without :Entity label")

        if count > 0 and not dry_run:
            session.run("""
                MATCH (n:SEMANTIC_ENTITY)
                WHERE NOT n:Entity
                SET n:Entity
            """)
            stats["entities_relabeled"] = count
            logger.info(f"  Added :Entity label to {count} nodes")

        # Step 2: Rename SEMANTIC_ENTITY -> SemanticEntity (PascalCase)
        logger.info("Step 2: Renaming SEMANTIC_ENTITY label to SemanticEntity...")
        query_2 = """
        MATCH (n:SEMANTIC_ENTITY)
        WHERE NOT n:SemanticEntity
        RETURN count(n) as total
        """
        result = session.run(query_2).single()
        count = result["total"] if result else 0
        logger.info(f"  Found {count} nodes to relabel to SemanticEntity")

        if count > 0 and not dry_run:
            session.run("""
                MATCH (n:SEMANTIC_ENTITY)
                WHERE NOT n:SemanticEntity
                SET n:SemanticEntity
                REMOVE n:SEMANTIC_ENTITY
            """)
            stats["entities_pascalcase"] = count
            logger.info(f"  Relabeled {count} nodes to SemanticEntity")

        # Step 3: Migrate SEMANTICALLY_RELATED -> RELATED_TO
        logger.info("Step 3: Migrating SEMANTICALLY_RELATED -> RELATED_TO...")
        query_3 = """
        MATCH ()-[r:SEMANTICALLY_RELATED]->()
        RETURN count(r) as total
        """
        result = session.run(query_3).single()
        count = result["total"] if result else 0
        logger.info(f"  Found {count} SEMANTICALLY_RELATED relationships to migrate")

        if count > 0 and not dry_run:
            # Create new RELATED_TO relationships with properties from old ones
            result = session.run("""
                MATCH (a)-[old:SEMANTICALLY_RELATED]->(b)
                CREATE (a)-[new:RELATED_TO]->(b)
                SET new = properties(old),
                    new.relation_subtype = 'semantic',
                    new.migrated_at = datetime()
                DELETE old
                RETURN count(new) as created
            """).single()
            stats["relationships_migrated"] = result["created"] if result else 0
            logger.info(f"  Migrated {stats['relationships_migrated']} relationships")

        # Step 4: Clean up any remaining SEMANTIC_ENTITY labels (should be 0 after step 2)
        remaining = session.run("""
            MATCH (n:SEMANTIC_ENTITY) RETURN count(n) as total
        """).single()
        remaining_count = remaining["total"] if remaining else 0
        if remaining_count > 0 and not dry_run:
            session.run("MATCH (n:SEMANTIC_ENTITY) REMOVE n:SEMANTIC_ENTITY")
            logger.info(f"  Cleaned up {remaining_count} remaining SEMANTIC_ENTITY labels")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Fix semantic relationships in Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without changing data")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "password"))
    parser.add_argument("--neo4j-database", default=os.getenv("NEO4J_DATABASE", "iudex"))
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY RUN MODE (no changes will be made) ===")

    try:
        driver = get_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)

        # Test connection
        with driver.session(database=args.neo4j_database) as session:
            session.run("RETURN 1")
        logger.info(f"Connected to Neo4j at {args.neo4j_uri} (database: {args.neo4j_database})")

        stats = migrate(driver, args.neo4j_database, dry_run=args.dry_run)

        logger.info("=== Migration Summary ===")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")

        driver.close()
        logger.info("Done.")

    except ImportError:
        logger.error("neo4j package not installed. Run: pip install neo4j>=5.20.0")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
