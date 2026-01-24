
from __future__ import annotations

import datetime as dt

from .services.opensearch_service import OpenSearchService
from .services.qdrant_service import QdrantService


def run_ttl_cleanup(
    *,
    os_svc: OpenSearchService,
    qd_svc: QdrantService,
    os_local_index: str,
    qd_local_collection: str,
    ttl_days: int,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=ttl_days)
    cutoff_epoch = int(cutoff.timestamp())

    try:
        os_svc.delete_local_older_than(os_local_index, cutoff)
    except Exception as e:
        print(f"[TTL] OpenSearch cleanup failed: {e}")

    try:
        qd_svc.delete_local_older_than(qd_local_collection, cutoff_epoch)
    except Exception as e:
        print(f"[TTL] Qdrant cleanup failed: {e}")
