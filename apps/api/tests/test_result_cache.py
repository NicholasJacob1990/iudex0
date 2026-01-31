"""Tests for ResultCache — TTL, invalidation, max_size, thread safety."""

import threading
import time

import pytest

from app.services.rag.core.result_cache import ResultCache, reset_result_cache


@pytest.fixture(autouse=True)
def _reset():
    reset_result_cache()
    yield
    reset_result_cache()


def _make_cache(**kwargs) -> ResultCache:
    return ResultCache(**kwargs)


class TestComputeKey:
    def test_deterministic(self):
        k1 = ResultCache.compute_key("q", "t1", "c1", ["i"], ["col"], "private")
        k2 = ResultCache.compute_key("q", "t1", "c1", ["i"], ["col"], "private")
        assert k1 == k2

    def test_different_query(self):
        k1 = ResultCache.compute_key("q1", "t", None, None, None, None)
        k2 = ResultCache.compute_key("q2", "t", None, None, None, None)
        assert k1 != k2

    def test_order_independent_indices(self):
        k1 = ResultCache.compute_key("q", "t", None, ["a", "b"], None, None)
        k2 = ResultCache.compute_key("q", "t", None, ["b", "a"], None, None)
        assert k1 == k2


class TestGetSet:
    def test_basic(self):
        cache = _make_cache()
        cache.set("k1", {"data": 1})
        assert cache.get("k1") == {"data": 1}

    def test_miss_returns_none(self):
        cache = _make_cache()
        assert cache.get("missing") is None

    def test_ttl_expiry(self):
        cache = _make_cache(ttl_seconds=0.1)
        cache.set("k1", "val")
        assert cache.get("k1") == "val"
        time.sleep(0.15)
        assert cache.get("k1") is None

    def test_max_size_eviction(self):
        cache = _make_cache(max_size=3)
        for i in range(5):
            cache.set(f"k{i}", i)
        assert cache.stats()["size"] <= 3


class TestInvalidation:
    def test_invalidate_tenant(self):
        cache = _make_cache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cleared = cache.invalidate_tenant("any")
        assert cleared == 2
        assert cache.get("k1") is None

    def test_invalidate_case(self):
        cache = _make_cache()
        cache.set("k1", "v1")
        cleared = cache.invalidate_case("t", "c")
        assert cleared == 1


class TestStats:
    def test_hit_miss_tracking(self):
        cache = _make_cache()
        cache.set("k1", "v")
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        s = cache.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["hit_rate"] == pytest.approx(0.5)


class TestThreadSafety:
    def test_concurrent_writes(self):
        cache = _make_cache(max_size=1000)
        errors = []

        def writer(start: int):
            try:
                for i in range(100):
                    cache.set(f"k{start + i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i * 100,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cache.stats()["size"] <= 1000
