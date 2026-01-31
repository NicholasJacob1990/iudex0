"""Tests for per-DB timeout behavior — slow DB returns [], pipeline continues."""

import asyncio

import pytest


async def _with_timeout(coro, timeout: float, name: str):
    """Mirrors the _with_timeout helper used in rag_pipeline.py."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return []


async def _slow_db(delay: float = 5.0):
    """Simulate a slow database that exceeds timeout."""
    await asyncio.sleep(delay)
    return [{"id": "should_not_return"}]


async def _fast_db():
    """Simulate a fast database response."""
    await asyncio.sleep(0.01)
    return [{"id": "doc1"}, {"id": "doc2"}]


@pytest.mark.asyncio
class TestWithTimeout:
    async def test_fast_db_returns_results(self):
        result = await _with_timeout(_fast_db(), timeout=1.0, name="fast")
        assert len(result) == 2
        assert result[0]["id"] == "doc1"

    async def test_slow_db_returns_empty(self):
        result = await _with_timeout(_slow_db(5.0), timeout=0.05, name="slow")
        assert result == []

    async def test_parallel_with_one_timeout(self):
        """One DB times out, others succeed — pipeline continues."""
        tasks = [
            _with_timeout(_fast_db(), timeout=1.0, name="fast_lexical"),
            _with_timeout(_slow_db(5.0), timeout=0.05, name="slow_vector"),
            _with_timeout(_fast_db(), timeout=1.0, name="fast_graph"),
        ]
        results = await asyncio.gather(*tasks)

        assert len(results[0]) == 2  # fast lexical succeeded
        assert results[1] == []      # slow vector timed out
        assert len(results[2]) == 2  # fast graph succeeded

    async def test_all_timeout_returns_empty_lists(self):
        tasks = [
            _with_timeout(_slow_db(5.0), timeout=0.05, name="db1"),
            _with_timeout(_slow_db(5.0), timeout=0.05, name="db2"),
        ]
        results = await asyncio.gather(*tasks)
        assert all(r == [] for r in results)

    async def test_min_sources_check(self):
        """After timeouts, check if minimum sources threshold is met."""
        min_sources_required = 1
        tasks = [
            _with_timeout(_fast_db(), timeout=1.0, name="lexical"),
            _with_timeout(_slow_db(5.0), timeout=0.05, name="vector"),
        ]
        results = await asyncio.gather(*tasks)

        non_empty = sum(1 for r in results if r)
        assert non_empty >= min_sources_required
