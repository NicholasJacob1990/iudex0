#!/usr/bin/env python3
"""
Re-ingest documents from a legacy Qdrant collection into a routed collection
using EmbeddingRouter (jurisdiction-aware providers).

Typical usage for Voyage Context 3 (BR):
  export VOYAGE_API_KEY=...
  export RAG_ROUTER_BR_PROVIDER=voyage_context
  export RAG_ROUTER_BR_COLLECTION=legal_br_ctx3
  python apps/api/scripts/migrate_qdrant_to_routed_collection.py --source lei --jurisdiction BR

Notes:
- This does NOT delete the source collection.
- It reads payload text from the source collection and upserts into the routed collection.
- It is best-effort and intended for controlled backfills / migrations.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def main_async(args: argparse.Namespace) -> int:
    # Ensure `app.*` imports work when executing from repo root.
    api_root = Path(__file__).resolve().parents[1]
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    import os

    from app.services.rag.embedding_router import (
        get_embedding_router,
        Jurisdiction,
        JURISDICTION_TO_COLLECTION,
    )
    from app.services.rag.storage.qdrant_service import get_qdrant_service

    try:
        juris = Jurisdiction(str(args.jurisdiction).strip().upper())
    except Exception:
        print(f"Invalid jurisdiction: {args.jurisdiction}", file=sys.stderr)
        return 2

    router = get_embedding_router()

    # Ensure target collection exists (best-effort).
    default_coll = JURISDICTION_TO_COLLECTION.get(juris, "general")
    env_coll = os.getenv(f"RAG_ROUTER_{juris.value}_COLLECTION", "").strip()
    target_coll = env_coll or default_coll
    try:
        q = get_qdrant_service()
        q.create_collection(target_coll)
    except Exception as e:
        print(f"Warning: failed to create target collection '{target_coll}': {e}", file=sys.stderr)

    res = await router.migrate_collection(
        source_collection=str(args.source).strip(),
        target_jurisdiction=juris,
        batch_size=int(args.batch_size),
        limit=int(args.limit) if int(args.limit) > 0 else None,
    )

    # Print a compact summary (JSON-like) without pulling extra deps.
    print(res)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True, help="Legacy Qdrant collection name (e.g. lei, juris, doutrina)")
    p.add_argument("--jurisdiction", required=True, help="Target jurisdiction (BR|EU|US|UK|INT|GENERAL)")
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--limit", type=int, default=0, help="Safety cap (0 = no limit)")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
