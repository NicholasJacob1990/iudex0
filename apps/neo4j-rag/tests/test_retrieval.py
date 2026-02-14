"""Tests for retrieval components (no Neo4j required)."""

from neo4j_rag.retrieval.hybrid import _rrf_fusion
from neo4j_rag.retrieval.traversal import RELATION_WHITELIST, RELATION_BLACKLIST


def test_rrf_fusion_basic():
    """RRF should combine scores from multiple result lists."""
    list1 = [("a", 0.9, "text_a"), ("b", 0.8, "text_b"), ("c", 0.7, "text_c")]
    list2 = [("b", 0.95, "text_b"), ("a", 0.85, "text_a"), ("d", 0.6, "text_d")]

    fused = _rrf_fusion(list1, list2, k=60)

    # 'a' and 'b' should be top (appear in both lists)
    ids = [cid for cid, _, _ in fused]
    assert "a" in ids[:3]
    assert "b" in ids[:3]
    # 'd' should be in results (only in list2)
    assert "d" in ids


def test_rrf_deduplication():
    """Same chunk in multiple lists should be deduplicated."""
    list1 = [("a", 0.9, "text_a")]
    list2 = [("a", 0.8, "text_a")]

    fused = _rrf_fusion(list1, list2, k=60)
    assert len(fused) == 1
    # Score should be sum of reciprocal ranks
    cid, score, _ = fused[0]
    assert cid == "a"
    assert score > 1.0 / 61  # More than single list contribution


def test_rrf_empty():
    """Empty input should return empty."""
    assert _rrf_fusion() == []
    assert _rrf_fusion([], []) == []


def test_whitelist_blacklist_disjoint():
    """Whitelist and blacklist should have no overlap."""
    overlap = RELATION_WHITELIST & RELATION_BLACKLIST
    assert len(overlap) == 0, f"Overlap found: {overlap}"


def test_co_ocorre_blacklisted():
    """CO_OCORRE and TRATA_DE must be blacklisted (main noise sources)."""
    assert "CO_OCORRE" in RELATION_BLACKLIST
    assert "TRATA_DE" in RELATION_BLACKLIST


def test_key_relations_whitelisted():
    """Critical legal relations must be whitelisted."""
    for rel in ["INTERPRETA", "FIXA_TESE", "FUNDAMENTA", "PERTENCE_A", "SUBDISPOSITIVO_DE"]:
        assert rel in RELATION_WHITELIST, f"{rel} missing from whitelist"
