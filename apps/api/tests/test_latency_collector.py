"""Tests for LatencyCollector — percentiles, sliding window, thread safety."""

import threading

import pytest

from app.services.rag.core.metrics import LatencyCollector, get_latency_collector


@pytest.fixture(autouse=True)
def _reset():
    get_latency_collector().reset()
    yield
    get_latency_collector().reset()


class TestRecord:
    def test_record_and_percentile(self):
        c = LatencyCollector()
        for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            c.record("search", v)
        assert c.percentile("search", 50) == pytest.approx(60, abs=10)
        assert c.percentile("search", 99) == pytest.approx(100, abs=5)

    def test_empty_stage(self):
        c = LatencyCollector()
        assert c.percentile("missing", 50) == 0.0

    def test_window_limit(self):
        c = LatencyCollector(window_size=5)
        for i in range(10):
            c.record("s", float(i))
        summary = c.summary()
        assert summary["s"]["count"] == 5


class TestSummary:
    def test_summary_fields(self):
        c = LatencyCollector()
        for v in [10.0, 20.0, 30.0]:
            c.record("stage_a", v)
        s = c.summary()
        assert "stage_a" in s
        assert set(s["stage_a"].keys()) == {"p50", "p95", "p99", "count", "avg"}
        assert s["stage_a"]["count"] == 3
        assert s["stage_a"]["avg"] == pytest.approx(20.0)

    def test_empty_summary(self):
        c = LatencyCollector()
        assert c.summary() == {}


class TestReset:
    def test_reset_clears(self):
        c = LatencyCollector()
        c.record("x", 1.0)
        c.reset()
        assert c.summary() == {}


class TestSingleton:
    def test_singleton(self):
        a = get_latency_collector()
        b = get_latency_collector()
        assert a is b


class TestThreadSafety:
    def test_concurrent_records(self):
        c = LatencyCollector()
        errors = []

        def writer(stage: str):
            try:
                for i in range(100):
                    c.record(stage, float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"s{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        s = c.summary()
        for i in range(4):
            assert s[f"s{i}"]["count"] == 100
