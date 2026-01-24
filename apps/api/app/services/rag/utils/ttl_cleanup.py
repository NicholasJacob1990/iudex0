"""
TTL Cleanup Job for Local RAG Data

Removes local data older than the configured TTL (default: 7 days) from:
- OpenSearch: rag-local index
- Qdrant: local_chunks collection

This module provides:
- cleanup_local_opensearch(): Delete expired documents from OpenSearch
- cleanup_local_qdrant(): Delete expired points from Qdrant
- run_ttl_cleanup(): Execute both cleanups
- schedule_ttl_cleanup(): Set up periodic execution
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.services.rag.config import get_rag_config

# =============================================================================
# CLEANUP STATISTICS
# =============================================================================


@dataclass
class CleanupStats:
    """Statistics for a single cleanup run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    opensearch_deleted: int = 0
    opensearch_errors: List[str] = field(default_factory=list)
    qdrant_deleted: int = 0
    qdrant_errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_deleted(self) -> int:
        return self.opensearch_deleted + self.qdrant_deleted

    @property
    def has_errors(self) -> bool:
        return bool(self.opensearch_errors or self.qdrant_errors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "opensearch_deleted": self.opensearch_deleted,
            "opensearch_errors": self.opensearch_errors,
            "qdrant_deleted": self.qdrant_deleted,
            "qdrant_errors": self.qdrant_errors,
            "total_deleted": self.total_deleted,
            "duration_seconds": self.duration_seconds,
            "has_errors": self.has_errors,
        }


# =============================================================================
# METRICS COLLECTOR
# =============================================================================


class CleanupMetrics:
    """Collects and exposes cleanup metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: List[CleanupStats] = []
        self._max_history = 100
        self._total_opensearch_deleted = 0
        self._total_qdrant_deleted = 0
        self._total_runs = 0
        self._total_errors = 0

    def record(self, stats: CleanupStats) -> None:
        """Record cleanup statistics."""
        with self._lock:
            self._runs.append(stats)
            if len(self._runs) > self._max_history:
                self._runs = self._runs[-self._max_history:]
            self._total_opensearch_deleted += stats.opensearch_deleted
            self._total_qdrant_deleted += stats.qdrant_deleted
            self._total_runs += 1
            if stats.has_errors:
                self._total_errors += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        with self._lock:
            recent = self._runs[-10:] if self._runs else []
            return {
                "total_runs": self._total_runs,
                "total_opensearch_deleted": self._total_opensearch_deleted,
                "total_qdrant_deleted": self._total_qdrant_deleted,
                "total_errors": self._total_errors,
                "recent_runs": [r.to_dict() for r in recent],
                "last_run": self._runs[-1].to_dict() if self._runs else None,
            }

    def get_last_run(self) -> Optional[CleanupStats]:
        """Get the most recent cleanup stats."""
        with self._lock:
            return self._runs[-1] if self._runs else None


# Global metrics instance
_metrics = CleanupMetrics()


def get_cleanup_metrics() -> CleanupMetrics:
    """Get the global cleanup metrics collector."""
    return _metrics


# =============================================================================
# OPENSEARCH CLEANUP
# =============================================================================


def _get_opensearch_client():
    """
    Create OpenSearch client with configuration from RAGConfig.

    Returns None if opensearch-py is not installed or connection fails.
    """
    config = get_rag_config()
    try:
        from opensearchpy import OpenSearch
    except ImportError:
        logger.warning("opensearch-py not installed, skipping OpenSearch cleanup")
        return None

    try:
        client = OpenSearch(
            hosts=[config.opensearch_url],
            http_auth=(config.opensearch_user, config.opensearch_password),
            use_ssl=config.opensearch_url.startswith("https"),
            verify_certs=config.opensearch_verify_certs,
            ssl_show_warn=False,
            timeout=30,
        )
        # Test connection
        client.info()
        return client
    except Exception as e:
        logger.error(f"Failed to connect to OpenSearch: {e}")
        return None


def cleanup_local_opensearch(
    ttl_days: Optional[int] = None,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> tuple[int, List[str]]:
    """
    Delete documents from rag-local index older than TTL.

    Args:
        ttl_days: Override TTL in days (default: from config)
        dry_run: If True, only count without deleting
        batch_size: Number of documents to delete per batch

    Returns:
        Tuple of (deleted_count, errors)
    """
    config = get_rag_config()
    ttl_days = ttl_days if ttl_days is not None else config.local_ttl_days
    index_name = config.opensearch_index_local

    logger.info(
        f"Starting OpenSearch cleanup: index={index_name}, ttl_days={ttl_days}, dry_run={dry_run}"
    )

    errors: List[str] = []
    deleted_count = 0

    client = _get_opensearch_client()
    if client is None:
        errors.append("OpenSearch client unavailable")
        return 0, errors

    # Calculate cutoff timestamp
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    cutoff_iso = cutoff.isoformat()

    # Query for documents older than TTL
    # Uses 'uploaded_at' field (ISO 8601 string) set during ingestion
    query = {
        "query": {
            "bool": {
                "must": [
                    {"range": {"uploaded_at": {"lt": cutoff_iso}}},
                ]
            }
        }
    }

    try:
        # Check if index exists
        if not client.indices.exists(index=index_name):
            logger.info(f"Index {index_name} does not exist, skipping")
            return 0, errors

        if dry_run:
            # Just count matching documents
            response = client.count(index=index_name, body=query)
            count = response.get("count", 0)
            logger.info(f"[DRY RUN] Would delete {count} documents from {index_name}")
            return count, errors

        # Use delete_by_query for efficient bulk deletion
        response = client.delete_by_query(
            index=index_name,
            body=query,
            conflicts="proceed",  # Continue on version conflicts
            wait_for_completion=True,
            refresh=True,
            scroll_size=batch_size,
        )

        deleted_count = response.get("deleted", 0)
        failures = response.get("failures", [])

        if failures:
            for failure in failures[:5]:  # Log first 5 failures
                errors.append(f"Delete failure: {failure}")
            if len(failures) > 5:
                errors.append(f"... and {len(failures) - 5} more failures")

        logger.info(
            f"OpenSearch cleanup complete: deleted={deleted_count}, "
            f"failures={len(failures)}, index={index_name}"
        )

    except Exception as e:
        error_msg = f"OpenSearch cleanup error: {e}"
        logger.error(error_msg)
        errors.append(error_msg)

    return deleted_count, errors


# =============================================================================
# QDRANT CLEANUP
# =============================================================================


def _get_qdrant_client():
    """
    Create Qdrant client with configuration from RAGConfig.

    Returns None if qdrant-client is not installed or connection fails.
    """
    config = get_rag_config()
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning("qdrant-client not installed, skipping Qdrant cleanup")
        return None

    try:
        api_key = config.qdrant_api_key if config.qdrant_api_key else None
        client = QdrantClient(
            url=config.qdrant_url,
            api_key=api_key,
            timeout=30,
        )
        # Test connection
        client.get_collections()
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        return None


def cleanup_local_qdrant(
    ttl_days: Optional[int] = None,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> tuple[int, List[str]]:
    """
    Delete points from local_chunks collection older than TTL.

    Args:
        ttl_days: Override TTL in days (default: from config)
        dry_run: If True, only count without deleting
        batch_size: Number of points to process per batch

    Returns:
        Tuple of (deleted_count, errors)
    """
    config = get_rag_config()
    ttl_days = ttl_days if ttl_days is not None else config.local_ttl_days
    collection_name = config.qdrant_collection_local

    logger.info(
        f"Starting Qdrant cleanup: collection={collection_name}, ttl_days={ttl_days}, dry_run={dry_run}"
    )

    errors: List[str] = []
    deleted_count = 0

    client = _get_qdrant_client()
    if client is None:
        errors.append("Qdrant client unavailable")
        return 0, errors

    try:
        from qdrant_client.models import Filter, FieldCondition, Range
    except ImportError:
        errors.append("qdrant-client models not available")
        return 0, errors

    # Calculate cutoff timestamp (Unix timestamp for Qdrant)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    cutoff_timestamp = cutoff.timestamp()
    cutoff_iso = cutoff.isoformat()

    try:
        # Check if collection exists
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]
        if collection_name not in collection_names:
            logger.info(f"Collection {collection_name} does not exist, skipping")
            return 0, errors

        # Build filter for old documents
        # Uses 'uploaded_at' field (Unix epoch integer) set during ingestion
        timestamp_fields = ["uploaded_at"]

        for ts_field in timestamp_fields:
            try:
                # Try with Unix timestamp first
                filter_condition = Filter(
                    must=[
                        FieldCondition(
                            key=ts_field,
                            range=Range(lt=cutoff_timestamp),
                        )
                    ]
                )

                # Count matching points
                count_result = client.count(
                    collection_name=collection_name,
                    count_filter=filter_condition,
                )

                if count_result.count > 0:
                    logger.info(
                        f"Found {count_result.count} expired points using field '{ts_field}'"
                    )

                    if dry_run:
                        deleted_count = count_result.count
                        logger.info(
                            f"[DRY RUN] Would delete {deleted_count} points from {collection_name}"
                        )
                        return deleted_count, errors

                    # Delete points matching the filter
                    delete_result = client.delete(
                        collection_name=collection_name,
                        points_selector=filter_condition,
                    )

                    # Qdrant delete returns operation info, count after
                    # Re-count to verify deletion
                    post_count = client.count(
                        collection_name=collection_name,
                        count_filter=filter_condition,
                    )
                    deleted_count = count_result.count - post_count.count

                    logger.info(
                        f"Qdrant cleanup complete: deleted={deleted_count}, "
                        f"collection={collection_name}"
                    )
                    return deleted_count, errors

            except Exception as field_error:
                # Try next field if this one doesn't exist
                logger.debug(f"Field '{ts_field}' not found or error: {field_error}")
                continue

        # Try ISO string format as fallback (for legacy data)
        for ts_field in ["uploaded_at"]:
            try:
                # Scroll through collection and filter manually
                # This is less efficient but more compatible
                offset = None
                points_to_delete = []

                while True:
                    scroll_result = client.scroll(
                        collection_name=collection_name,
                        limit=batch_size,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )

                    points, next_offset = scroll_result

                    if not points:
                        break

                    for point in points:
                        payload = point.payload or {}
                        ts_value = payload.get(ts_field)
                        if ts_value:
                            try:
                                if isinstance(ts_value, str):
                                    point_time = datetime.fromisoformat(
                                        ts_value.replace("Z", "+00:00")
                                    )
                                elif isinstance(ts_value, (int, float)):
                                    point_time = datetime.fromtimestamp(
                                        ts_value, tz=timezone.utc
                                    )
                                else:
                                    continue

                                if point_time < cutoff:
                                    points_to_delete.append(point.id)
                            except (ValueError, TypeError):
                                continue

                    if next_offset is None:
                        break
                    offset = next_offset

                if points_to_delete:
                    logger.info(f"Found {len(points_to_delete)} expired points via scroll")

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would delete {len(points_to_delete)} points"
                        )
                        return len(points_to_delete), errors

                    # Delete in batches
                    for i in range(0, len(points_to_delete), batch_size):
                        batch = points_to_delete[i:i + batch_size]
                        client.delete(
                            collection_name=collection_name,
                            points_selector=batch,
                        )
                        deleted_count += len(batch)

                    logger.info(f"Qdrant cleanup complete: deleted={deleted_count}")
                    return deleted_count, errors

            except Exception as scroll_error:
                logger.debug(f"Scroll cleanup with '{ts_field}' failed: {scroll_error}")
                continue

        logger.info("No timestamp fields found or no expired documents")
        return 0, errors

    except Exception as e:
        error_msg = f"Qdrant cleanup error: {e}"
        logger.error(error_msg)
        errors.append(error_msg)

    return deleted_count, errors


# =============================================================================
# COMBINED CLEANUP
# =============================================================================


def run_ttl_cleanup(
    ttl_days: Optional[int] = None,
    dry_run: bool = False,
    skip_opensearch: bool = False,
    skip_qdrant: bool = False,
) -> CleanupStats:
    """
    Run TTL cleanup on both OpenSearch and Qdrant.

    Args:
        ttl_days: Override TTL in days (default: from config)
        dry_run: If True, only count without deleting
        skip_opensearch: Skip OpenSearch cleanup
        skip_qdrant: Skip Qdrant cleanup

    Returns:
        CleanupStats with results from both systems
    """
    stats = CleanupStats()

    config = get_rag_config()
    ttl_days = ttl_days if ttl_days is not None else config.local_ttl_days

    logger.info(
        f"Starting TTL cleanup: ttl_days={ttl_days}, dry_run={dry_run}, "
        f"skip_opensearch={skip_opensearch}, skip_qdrant={skip_qdrant}"
    )

    start_time = time.monotonic()

    # OpenSearch cleanup
    if not skip_opensearch:
        try:
            os_deleted, os_errors = cleanup_local_opensearch(
                ttl_days=ttl_days,
                dry_run=dry_run,
            )
            stats.opensearch_deleted = os_deleted
            stats.opensearch_errors = os_errors
        except Exception as e:
            logger.exception("OpenSearch cleanup failed")
            stats.opensearch_errors.append(f"Unexpected error: {e}")
    else:
        logger.info("Skipping OpenSearch cleanup")

    # Qdrant cleanup
    if not skip_qdrant:
        try:
            qd_deleted, qd_errors = cleanup_local_qdrant(
                ttl_days=ttl_days,
                dry_run=dry_run,
            )
            stats.qdrant_deleted = qd_deleted
            stats.qdrant_errors = qd_errors
        except Exception as e:
            logger.exception("Qdrant cleanup failed")
            stats.qdrant_errors.append(f"Unexpected error: {e}")
    else:
        logger.info("Skipping Qdrant cleanup")

    # Finalize stats
    stats.completed_at = datetime.now(timezone.utc)
    stats.duration_seconds = time.monotonic() - start_time

    # Record metrics
    _metrics.record(stats)

    logger.info(
        f"TTL cleanup complete: opensearch_deleted={stats.opensearch_deleted}, "
        f"qdrant_deleted={stats.qdrant_deleted}, duration={stats.duration_seconds:.2f}s, "
        f"errors={stats.has_errors}"
    )

    return stats


async def run_ttl_cleanup_async(
    ttl_days: Optional[int] = None,
    dry_run: bool = False,
    skip_opensearch: bool = False,
    skip_qdrant: bool = False,
) -> CleanupStats:
    """
    Async wrapper for TTL cleanup.

    Runs cleanup in thread pool to avoid blocking event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: run_ttl_cleanup(
            ttl_days=ttl_days,
            dry_run=dry_run,
            skip_opensearch=skip_opensearch,
            skip_qdrant=skip_qdrant,
        ),
    )


# =============================================================================
# SCHEDULER
# =============================================================================


class TTLCleanupScheduler:
    """
    Scheduler for periodic TTL cleanup execution.

    Supports two modes:
    1. Simple background thread with sleep loop
    2. APScheduler integration (if available)
    """

    def __init__(
        self,
        interval_hours: Optional[float] = None,
        ttl_days: Optional[int] = None,
        on_complete: Optional[Callable[[CleanupStats], None]] = None,
    ) -> None:
        """
        Initialize scheduler.

        Args:
            interval_hours: Hours between cleanup runs (default: from config)
            ttl_days: TTL in days (default: from config)
            on_complete: Optional callback after each cleanup
        """
        config = get_rag_config()
        self.interval_hours = (
            interval_hours if interval_hours is not None
            else config.ttl_cleanup_interval_hours
        )
        self.ttl_days = ttl_days if ttl_days is not None else config.local_ttl_days
        self.on_complete = on_complete

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._scheduler = None

    def _run_cleanup_job(self) -> None:
        """Execute cleanup and call callback."""
        try:
            stats = run_ttl_cleanup(ttl_days=self.ttl_days)
            if self.on_complete:
                self.on_complete(stats)
        except Exception as e:
            logger.exception(f"Scheduled TTL cleanup failed: {e}")

    def _simple_loop(self) -> None:
        """Simple sleep-based scheduler loop."""
        interval_seconds = self.interval_hours * 3600

        logger.info(
            f"TTL cleanup scheduler started: interval={self.interval_hours}h, "
            f"ttl_days={self.ttl_days}"
        )

        # Run initial cleanup after short delay
        if not self._stop_event.wait(60):  # 1 minute initial delay
            self._run_cleanup_job()

        while not self._stop_event.is_set():
            # Wait for interval or stop signal
            if self._stop_event.wait(interval_seconds):
                break
            self._run_cleanup_job()

        logger.info("TTL cleanup scheduler stopped")

    def start(self, use_apscheduler: bool = True) -> None:
        """
        Start the cleanup scheduler.

        Args:
            use_apscheduler: Try to use APScheduler if available
        """
        if self._running:
            logger.warning("TTL cleanup scheduler already running")
            return

        self._running = True
        self._stop_event.clear()

        # Try APScheduler first if requested
        if use_apscheduler:
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
                from apscheduler.triggers.interval import IntervalTrigger

                self._scheduler = BackgroundScheduler()
                self._scheduler.add_job(
                    self._run_cleanup_job,
                    trigger=IntervalTrigger(hours=self.interval_hours),
                    id="ttl_cleanup",
                    name="TTL Cleanup Job",
                    replace_existing=True,
                )
                self._scheduler.start()

                logger.info(
                    f"TTL cleanup scheduler started with APScheduler: "
                    f"interval={self.interval_hours}h"
                )

                # Run initial cleanup
                self._scheduler.add_job(
                    self._run_cleanup_job,
                    id="ttl_cleanup_initial",
                    name="TTL Cleanup Initial Run",
                )
                return

            except ImportError:
                logger.info("APScheduler not available, using simple loop")
            except Exception as e:
                logger.warning(f"APScheduler setup failed, using simple loop: {e}")

        # Fall back to simple loop
        self._thread = threading.Thread(
            target=self._simple_loop,
            name="ttl-cleanup-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        """
        Stop the cleanup scheduler.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown
        """
        if not self._running:
            return

        logger.info("Stopping TTL cleanup scheduler...")
        self._running = False

        if self._scheduler:
            try:
                self._scheduler.shutdown(wait=True)
            except Exception as e:
                logger.warning(f"APScheduler shutdown error: {e}")
            self._scheduler = None

        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("TTL cleanup scheduler thread did not stop gracefully")
            self._thread = None

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running


# Global scheduler instance
_scheduler: Optional[TTLCleanupScheduler] = None


def schedule_ttl_cleanup(
    interval_hours: Optional[float] = None,
    ttl_days: Optional[int] = None,
    on_complete: Optional[Callable[[CleanupStats], None]] = None,
    use_apscheduler: bool = True,
) -> TTLCleanupScheduler:
    """
    Set up periodic TTL cleanup execution.

    Creates and starts a global scheduler instance.

    Args:
        interval_hours: Hours between cleanup runs (default: from config)
        ttl_days: TTL in days (default: from config)
        on_complete: Optional callback after each cleanup
        use_apscheduler: Try to use APScheduler if available

    Returns:
        The scheduler instance
    """
    global _scheduler

    # Stop existing scheduler if running
    if _scheduler is not None and _scheduler.is_running:
        _scheduler.stop()

    _scheduler = TTLCleanupScheduler(
        interval_hours=interval_hours,
        ttl_days=ttl_days,
        on_complete=on_complete,
    )
    _scheduler.start(use_apscheduler=use_apscheduler)

    return _scheduler


def stop_ttl_cleanup_scheduler() -> None:
    """Stop the global TTL cleanup scheduler."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None


def get_ttl_cleanup_scheduler() -> Optional[TTLCleanupScheduler]:
    """Get the global TTL cleanup scheduler instance."""
    return _scheduler


# =============================================================================
# CELERY TASK (Optional Integration)
# =============================================================================


def create_celery_task():
    """
    Create a Celery task for TTL cleanup.

    Call this from your Celery app configuration to register the task.

    Example:
        from app.services.rag.utils.ttl_cleanup import create_celery_task
        ttl_cleanup_task = create_celery_task()

        # Then schedule with Celery Beat:
        app.conf.beat_schedule = {
            'ttl-cleanup-every-6-hours': {
                'task': 'ttl_cleanup',
                'schedule': crontab(hour='*/6'),
            },
        }
    """
    try:
        from celery import shared_task

        @shared_task(name="ttl_cleanup", bind=True, max_retries=3)
        def ttl_cleanup_task(
            self,
            ttl_days: Optional[int] = None,
            dry_run: bool = False,
        ):
            """Celery task for TTL cleanup."""
            try:
                stats = run_ttl_cleanup(ttl_days=ttl_days, dry_run=dry_run)
                return stats.to_dict()
            except Exception as e:
                logger.error(f"Celery TTL cleanup failed: {e}")
                raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return ttl_cleanup_task

    except ImportError:
        logger.debug("Celery not available, skipping task creation")
        return None


# =============================================================================
# CLI ENTRY POINT
# =============================================================================


def main() -> None:
    """CLI entry point for manual cleanup execution."""
    import argparse

    parser = argparse.ArgumentParser(description="TTL Cleanup for Local RAG Data")
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=None,
        help="TTL in days (default: from config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count without deleting",
    )
    parser.add_argument(
        "--skip-opensearch",
        action="store_true",
        help="Skip OpenSearch cleanup",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant cleanup",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run as scheduled job (blocking)",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help="Schedule interval in hours",
    )

    args = parser.parse_args()

    if args.schedule:
        # Run as scheduled job
        scheduler = schedule_ttl_cleanup(
            interval_hours=args.interval_hours,
            ttl_days=args.ttl_days,
            on_complete=lambda s: logger.info(f"Cleanup complete: {s.to_dict()}"),
            use_apscheduler=True,
        )

        try:
            # Keep main thread alive
            while scheduler.is_running:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            scheduler.stop()
    else:
        # Run single cleanup
        stats = run_ttl_cleanup(
            ttl_days=args.ttl_days,
            dry_run=args.dry_run,
            skip_opensearch=args.skip_opensearch,
            skip_qdrant=args.skip_qdrant,
        )

        print(f"\nCleanup Results:")
        print(f"  OpenSearch deleted: {stats.opensearch_deleted}")
        print(f"  Qdrant deleted: {stats.qdrant_deleted}")
        print(f"  Total deleted: {stats.total_deleted}")
        print(f"  Duration: {stats.duration_seconds:.2f}s")

        if stats.has_errors:
            print(f"\nErrors:")
            for err in stats.opensearch_errors + stats.qdrant_errors:
                print(f"  - {err}")


if __name__ == "__main__":
    main()
