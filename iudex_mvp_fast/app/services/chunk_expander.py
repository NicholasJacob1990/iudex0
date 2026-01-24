"""
Chunk expansion service for RAG pipelines.

Provides parent chunk expansion and neighbor retrieval to add
context around matched chunks, improving answer quality for
questions that span multiple chunks.

Features:
- Parent chunk expansion (get surrounding chunks from same document)
- Neighbor expansion (+/- N chunks from each hit)
- Configurable window size
- Maximum extra chunks limit to control context size
- Metadata preservation through transformations
- Deduplication of expanded chunks
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ChunkExpander")


@dataclass
class ExpansionConfig:
    """Configuration for the chunk expander."""

    # Window size: number of chunks to fetch before and after each hit
    window: int = 1

    # Maximum extra chunks to add per original hit
    max_extra_per_hit: int = 2

    # Maximum total extra chunks across all hits
    max_extra_total: int = 10

    # Whether to preserve original chunk order or sort by position
    preserve_order: bool = True

    # Whether to merge adjacent expanded chunks
    merge_adjacent: bool = True

    # Separator for merged chunks
    merge_separator: str = "\n\n"

    # Maximum characters after expansion (0 = no limit)
    max_total_chars: int = 0

    @classmethod
    def from_env(cls) -> "ExpansionConfig":
        """Load configuration from environment variables."""
        return cls(
            window=int(os.getenv("EXPANDER_WINDOW", "1")),
            max_extra_per_hit=int(os.getenv("EXPANDER_MAX_EXTRA_PER_HIT", "2")),
            max_extra_total=int(os.getenv("EXPANDER_MAX_EXTRA_TOTAL", "10")),
            preserve_order=os.getenv("EXPANDER_PRESERVE_ORDER", "true").lower() in ("1", "true", "yes"),
            merge_adjacent=os.getenv("EXPANDER_MERGE_ADJACENT", "true").lower() in ("1", "true", "yes"),
            merge_separator=os.getenv("EXPANDER_MERGE_SEP", "\n\n"),
            max_total_chars=int(os.getenv("EXPANDER_MAX_CHARS", "0")),
        )


@dataclass
class ExpansionResult:
    """Result of an expansion operation."""

    results: List[Dict[str, Any]]
    original_count: int
    expanded_count: int
    extra_chunks_added: int
    merged_groups: int
    duration_ms: float = 0.0


@dataclass
class ChunkLocation:
    """Location information for a chunk within its source document."""

    doc_id: str
    chunk_index: int
    total_chunks: Optional[int] = None


class ChunkExpander:
    """
    Expands retrieval results by fetching neighboring chunks.

    Provides two main expansion strategies:
    1. Window expansion: Fetch +/- N chunks around each hit
    2. Parent expansion: Fetch all chunks from the same document section

    Requires a chunk fetcher function to retrieve additional chunks.
    """

    def __init__(
        self,
        config: Optional[ExpansionConfig] = None,
        chunk_fetcher: Optional[Callable[[str, int], Optional[Dict[str, Any]]]] = None,
    ):
        """
        Initialize the expander.

        Args:
            config: Expansion configuration
            chunk_fetcher: Function(doc_id, chunk_index) -> chunk dict or None
        """
        self.config = config or ExpansionConfig.from_env()
        self._chunk_fetcher = chunk_fetcher

    def set_chunk_fetcher(
        self,
        fetcher: Callable[[str, int], Optional[Dict[str, Any]]],
    ) -> None:
        """Set the chunk fetcher function."""
        self._chunk_fetcher = fetcher

    def _extract_location(self, chunk: Dict[str, Any]) -> Optional[ChunkLocation]:
        """Extract location info from chunk metadata."""
        metadata = chunk.get("metadata", {}) or {}

        # Try different common field names
        doc_id = (
            chunk.get("doc_id")
            or metadata.get("doc_id")
            or metadata.get("document_id")
            or metadata.get("source_id")
        )

        chunk_index = (
            chunk.get("chunk_index")
            or metadata.get("chunk_index")
            or metadata.get("chunk_idx")
            or metadata.get("index")
        )

        if doc_id is None or chunk_index is None:
            return None

        try:
            chunk_index = int(chunk_index)
        except (ValueError, TypeError):
            return None

        total = metadata.get("total_chunks")
        if total is not None:
            try:
                total = int(total)
            except (ValueError, TypeError):
                total = None

        return ChunkLocation(
            doc_id=str(doc_id),
            chunk_index=chunk_index,
            total_chunks=total,
        )

    def _fetch_neighbor(
        self,
        doc_id: str,
        chunk_index: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a neighbor chunk using the configured fetcher."""
        if not self._chunk_fetcher:
            return None

        try:
            return self._chunk_fetcher(doc_id, chunk_index)
        except Exception as e:
            logger.warning(f"Failed to fetch chunk {doc_id}:{chunk_index}: {e}")
            return None

    def _get_neighbor_indices(
        self,
        center: int,
        window: int,
        total: Optional[int] = None,
    ) -> List[int]:
        """
        Calculate neighbor indices for a given center position.

        Returns indices in order: center, center-1, center+1, center-2, center+2, ...
        """
        indices = []
        for offset in range(1, window + 1):
            before = center - offset
            after = center + offset

            if before >= 0:
                indices.append(before)
            if total is None or after < total:
                indices.append(after)

        return indices

    def expand_chunk(
        self,
        chunk: Dict[str, Any],
        window: Optional[int] = None,
        max_extra: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Expand a single chunk by fetching neighbors.

        Args:
            chunk: The chunk to expand
            window: Override for window size
            max_extra: Override for max extra chunks

        Returns:
            List of chunks including original and neighbors
        """
        window = window if window is not None else self.config.window
        max_extra = max_extra if max_extra is not None else self.config.max_extra_per_hit

        location = self._extract_location(chunk)
        if not location:
            return [chunk]

        if not self._chunk_fetcher:
            return [chunk]

        # Get neighbor indices
        neighbor_indices = self._get_neighbor_indices(
            location.chunk_index,
            window,
            location.total_chunks,
        )

        # Fetch neighbors up to max_extra
        neighbors: List[Dict[str, Any]] = []
        for idx in neighbor_indices[:max_extra]:
            neighbor = self._fetch_neighbor(location.doc_id, idx)
            if neighbor:
                # Mark as expanded neighbor
                neighbor = neighbor.copy()
                neighbor["is_expansion"] = True
                neighbor["expansion_source"] = location.chunk_index
                neighbors.append(neighbor)

        if not neighbors:
            return [chunk]

        # Combine and sort by chunk index
        all_chunks = [chunk] + neighbors
        all_chunks.sort(key=lambda c: self._extract_location(c).chunk_index if self._extract_location(c) else 0)

        return all_chunks

    def _merge_adjacent_chunks(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge adjacent chunks from the same document."""
        if len(chunks) <= 1:
            return chunks

        # Group by doc_id
        groups: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
        for chunk in chunks:
            location = self._extract_location(chunk)
            if location:
                key = location.doc_id
                if key not in groups:
                    groups[key] = []
                groups[key].append((location.chunk_index, chunk))

        merged_results: List[Dict[str, Any]] = []

        for doc_id, indexed_chunks in groups.items():
            # Sort by chunk index
            indexed_chunks.sort(key=lambda x: x[0])

            # Find contiguous sequences
            sequences: List[List[Dict[str, Any]]] = []
            current_seq: List[Dict[str, Any]] = []
            prev_idx = -999

            for idx, chunk in indexed_chunks:
                if idx == prev_idx + 1:
                    current_seq.append(chunk)
                else:
                    if current_seq:
                        sequences.append(current_seq)
                    current_seq = [chunk]
                prev_idx = idx

            if current_seq:
                sequences.append(current_seq)

            # Merge each sequence
            for seq in sequences:
                if len(seq) == 1:
                    merged_results.append(seq[0])
                else:
                    # Merge texts
                    merged_text = self.config.merge_separator.join(
                        c.get("text", "") for c in seq if c.get("text")
                    )

                    # Use first chunk as base, update text
                    merged = seq[0].copy()
                    merged["text"] = merged_text
                    merged["merged_from"] = [
                        self._extract_location(c).chunk_index if self._extract_location(c) else i
                        for i, c in enumerate(seq)
                    ]
                    merged["merge_count"] = len(seq)

                    # Update metadata
                    if "metadata" in merged:
                        merged["metadata"] = merged["metadata"].copy()
                        merged["metadata"]["merged"] = True
                        merged["metadata"]["merge_count"] = len(seq)

                    merged_results.append(merged)

        return merged_results

    def expand_results(
        self,
        results: List[Dict[str, Any]],
        window: Optional[int] = None,
        max_extra_per_hit: Optional[int] = None,
        max_extra_total: Optional[int] = None,
    ) -> ExpansionResult:
        """
        Expand all retrieval results by fetching neighbors.

        Args:
            results: List of retrieval results
            window: Override for window size
            max_extra_per_hit: Override for max extra per hit
            max_extra_total: Override for max total extra

        Returns:
            ExpansionResult with expanded results and statistics
        """
        import time
        start_time = time.perf_counter()

        if not results:
            return ExpansionResult(
                results=[],
                original_count=0,
                expanded_count=0,
                extra_chunks_added=0,
                merged_groups=0,
                duration_ms=0.0,
            )

        window = window if window is not None else self.config.window
        max_per_hit = max_extra_per_hit if max_extra_per_hit is not None else self.config.max_extra_per_hit
        max_total = max_extra_total if max_extra_total is not None else self.config.max_extra_total

        original_count = len(results)
        seen_chunk_uids: Set[str] = set()
        expanded_results: List[Dict[str, Any]] = []
        extra_added = 0

        for chunk in results:
            # Track by chunk_uid to avoid duplicates
            chunk_uid = chunk.get("chunk_uid")
            if chunk_uid and chunk_uid in seen_chunk_uids:
                continue
            if chunk_uid:
                seen_chunk_uids.add(chunk_uid)

            # Add original chunk
            expanded_results.append(chunk)

            # Check if we've hit the total limit
            if extra_added >= max_total:
                continue

            # Calculate how many more we can add
            remaining = max_total - extra_added
            current_max = min(max_per_hit, remaining)

            # Expand this chunk
            expanded = self.expand_chunk(chunk, window, current_max)

            # Add non-duplicate neighbors
            for neighbor in expanded[1:]:  # Skip first (original)
                neighbor_uid = neighbor.get("chunk_uid")
                if neighbor_uid and neighbor_uid in seen_chunk_uids:
                    continue
                if neighbor_uid:
                    seen_chunk_uids.add(neighbor_uid)

                expanded_results.append(neighbor)
                extra_added += 1

                if extra_added >= max_total:
                    break

        # Optionally merge adjacent chunks
        merged_groups = 0
        if self.config.merge_adjacent:
            before_merge = len(expanded_results)
            expanded_results = self._merge_adjacent_chunks(expanded_results)
            merged_groups = before_merge - len(expanded_results)

        # Enforce max chars if configured
        if self.config.max_total_chars > 0:
            total_chars = 0
            filtered = []
            for chunk in expanded_results:
                text_len = len(chunk.get("text", ""))
                if total_chars + text_len <= self.config.max_total_chars:
                    filtered.append(chunk)
                    total_chars += text_len
            expanded_results = filtered

        # Restore original order if configured
        if self.config.preserve_order and not self.config.merge_adjacent:
            # Keep original results in their order, append expansions
            original_uids = {r.get("chunk_uid") for r in results if r.get("chunk_uid")}
            original_ordered = [r for r in expanded_results if r.get("chunk_uid") in original_uids]
            expansions = [r for r in expanded_results if r.get("chunk_uid") not in original_uids]
            expanded_results = original_ordered + expansions

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Expanded {original_count} -> {len(expanded_results)} chunks "
            f"(+{extra_added} neighbors, {merged_groups} merges) in {duration_ms:.1f}ms"
        )

        return ExpansionResult(
            results=expanded_results,
            original_count=original_count,
            expanded_count=len(expanded_results),
            extra_chunks_added=extra_added,
            merged_groups=merged_groups,
            duration_ms=duration_ms,
        )


class ParentChunkExpander(ChunkExpander):
    """
    Specialized expander for parent-child chunk relationships.

    Handles hierarchical document structures where chunks may have
    parent chunks (e.g., paragraph -> section -> document).
    """

    def __init__(
        self,
        config: Optional[ExpansionConfig] = None,
        chunk_fetcher: Optional[Callable[[str, int], Optional[Dict[str, Any]]]] = None,
        parent_fetcher: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ):
        """
        Initialize the parent expander.

        Args:
            config: Expansion configuration
            chunk_fetcher: Function(doc_id, chunk_index) -> chunk dict
            parent_fetcher: Function(chunk_uid) -> parent chunk dict
        """
        super().__init__(config, chunk_fetcher)
        self._parent_fetcher = parent_fetcher

    def set_parent_fetcher(
        self,
        fetcher: Callable[[str], Optional[Dict[str, Any]]],
    ) -> None:
        """Set the parent fetcher function."""
        self._parent_fetcher = fetcher

    def _get_parent(self, chunk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch parent chunk if available."""
        if not self._parent_fetcher:
            return None

        metadata = chunk.get("metadata", {}) or {}
        parent_uid = (
            chunk.get("parent_chunk_uid")
            or metadata.get("parent_chunk_uid")
            or metadata.get("parent_id")
        )

        if not parent_uid:
            return None

        try:
            return self._parent_fetcher(str(parent_uid))
        except Exception as e:
            logger.warning(f"Failed to fetch parent chunk {parent_uid}: {e}")
            return None

    def expand_to_parent(
        self,
        chunk: Dict[str, Any],
        include_siblings: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Expand a chunk to include its parent context.

        Args:
            chunk: The chunk to expand
            include_siblings: Whether to include sibling chunks

        Returns:
            List of chunks including parent and optionally siblings
        """
        parent = self._get_parent(chunk)
        if not parent:
            return [chunk]

        result = [chunk]

        # Add parent
        parent = parent.copy()
        parent["is_parent"] = True
        parent["child_chunk_uid"] = chunk.get("chunk_uid")
        result.append(parent)

        # Optionally add siblings via neighbor expansion
        if include_siblings:
            expanded = self.expand_chunk(chunk, window=1, max_extra=2)
            for sibling in expanded[1:]:
                sibling = sibling.copy()
                sibling["is_sibling"] = True
                result.append(sibling)

        return result


# Convenience function for simple usage
def expand_chunks(
    results: List[Dict[str, Any]],
    window: int = 1,
    max_extra: int = 10,
    chunk_fetcher: Optional[Callable[[str, int], Optional[Dict[str, Any]]]] = None,
    config: Optional[ExpansionConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to expand retrieval results.

    Args:
        results: List of retrieval results
        window: Number of neighbors to fetch on each side
        max_extra: Maximum extra chunks to add
        chunk_fetcher: Function to fetch additional chunks
        config: Optional expansion configuration

    Returns:
        Expanded list of results
    """
    expander = ChunkExpander(config, chunk_fetcher)
    result = expander.expand_results(results, window=window, max_extra_total=max_extra)
    return result.results


# Factory for creating an expander with storage backends
def create_expander_with_qdrant(
    qdrant_service: Any,
    collection: str,
    config: Optional[ExpansionConfig] = None,
) -> ChunkExpander:
    """
    Create a ChunkExpander with Qdrant as the chunk fetcher backend.

    Args:
        qdrant_service: QdrantService instance
        collection: Collection name
        config: Optional expansion configuration

    Returns:
        Configured ChunkExpander
    """
    from qdrant_client.http import models as qm

    def fetch_chunk(doc_id: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific chunk from Qdrant by doc_id and chunk_index."""
        try:
            filter_cond = qm.Filter(
                must=[
                    qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id)),
                    qm.FieldCondition(key="chunk_index", match=qm.MatchValue(value=chunk_index)),
                ]
            )

            results = qdrant_service.client.scroll(
                collection_name=collection,
                scroll_filter=filter_cond,
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            points = results[0] if results else []
            if not points:
                return None

            point = points[0]
            payload = point.payload or {}
            return {
                "chunk_uid": payload.get("chunk_uid") or str(point.id),
                "text": payload.get("text", ""),
                "metadata": {k: v for k, v in payload.items() if k != "text"},
            }
        except Exception as e:
            logger.warning(f"Qdrant chunk fetch failed: {e}")
            return None

    return ChunkExpander(config, fetch_chunk)


def create_expander_with_opensearch(
    opensearch_service: Any,
    index: str,
    config: Optional[ExpansionConfig] = None,
) -> ChunkExpander:
    """
    Create a ChunkExpander with OpenSearch as the chunk fetcher backend.

    Args:
        opensearch_service: OpenSearchService instance
        index: Index name
        config: Optional expansion configuration

    Returns:
        Configured ChunkExpander
    """

    def fetch_chunk(doc_id: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific chunk from OpenSearch by doc_id and chunk_index."""
        try:
            body = {
                "size": 1,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"doc_id": doc_id}},
                            {"term": {"chunk_index": chunk_index}},
                        ]
                    }
                },
            }

            resp = opensearch_service.client.search(index=index, body=body)
            hits = resp.get("hits", {}).get("hits", [])

            if not hits:
                return None

            src = hits[0].get("_source", {})
            return {
                "chunk_uid": src.get("chunk_uid") or hits[0].get("_id"),
                "text": src.get("text", ""),
                "metadata": {k: v for k, v in src.items() if k != "text"},
            }
        except Exception as e:
            logger.warning(f"OpenSearch chunk fetch failed: {e}")
            return None

    return ChunkExpander(config, fetch_chunk)
