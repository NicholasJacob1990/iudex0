import pytest

from app.services.ai.observability.metrics import (
    AgentObservabilityMetrics,
    get_observability_metrics,
    reset_observability_metrics,
)


def test_snapshot_empty_defaults():
    metrics = AgentObservabilityMetrics(max_points=10)
    snapshot = metrics.snapshot()

    assert snapshot["requests"]["total"] == 0
    assert snapshot["requests"]["success_count"] == 0
    assert snapshot["requests"]["success_rate"] == 0.0
    assert snapshot["requests"]["cost_avg_usd"] == 0.0
    assert snapshot["tool_approvals"]["total"] == 0
    assert snapshot["fallback_rates"] == {}


def test_records_request_stats_and_percentiles():
    metrics = AgentObservabilityMetrics(max_points=10)
    metrics.record_request(execution_path="router:claude_agent", latency_ms=100, success=True, cost_usd=0.2)
    metrics.record_request(execution_path="router:claude_agent", latency_ms=200, success=False, cost_usd=0.4)
    metrics.record_request(execution_path="router:langgraph", latency_ms=300, success=True, cost_usd=0.6)

    snapshot = metrics.snapshot()
    latency = snapshot["requests"]["latency_ms"]

    assert snapshot["requests"]["total"] == 3
    assert snapshot["requests"]["success_count"] == 2
    assert snapshot["requests"]["success_rate"] == pytest.approx(2 / 3)
    assert snapshot["requests"]["cost_avg_usd"] == pytest.approx(0.4)
    assert latency["min"] == 100
    assert latency["avg"] == pytest.approx(200.0)
    assert latency["p50"] == pytest.approx(200.0)
    assert latency["p95"] == pytest.approx(290.0)
    assert latency["p99"] == pytest.approx(298.0)
    assert latency["max"] == 300


def test_records_tool_approval_and_fallback_rates():
    metrics = AgentObservabilityMetrics(max_points=10)
    metrics.record_tool_approval("allow")
    metrics.record_tool_approval("ask")
    metrics.record_tool_approval("deny")
    metrics.record_tool_approval("ignored")

    metrics.record_fallback("sdk_to_raw", used_fallback=False)
    metrics.record_fallback("sdk_to_raw", used_fallback=True)
    metrics.record_fallback("sdk_to_raw", used_fallback=True)

    snapshot = metrics.snapshot()
    approvals = snapshot["tool_approvals"]
    sdk_fallback = snapshot["fallback_rates"]["sdk_to_raw"]

    assert approvals["total"] == 3
    assert approvals["allow"] == 1
    assert approvals["ask"] == 1
    assert approvals["deny"] == 1
    assert approvals["allow_rate"] == pytest.approx(1 / 3)
    assert approvals["ask_rate"] == pytest.approx(1 / 3)
    assert approvals["deny_rate"] == pytest.approx(1 / 3)

    assert sdk_fallback["attempts"] == 3
    assert sdk_fallback["fallbacks"] == 2
    assert sdk_fallback["rate"] == pytest.approx(2 / 3)


def test_singleton_reset_clears_existing_data():
    reset_observability_metrics()
    singleton = get_observability_metrics()
    singleton.record_request(execution_path="router:test", latency_ms=10, success=True, cost_usd=1.0)
    singleton.record_tool_approval("allow")
    singleton.record_fallback("sdk_to_raw", used_fallback=True)

    pre_reset = singleton.snapshot()
    assert pre_reset["requests"]["total"] == 1
    assert pre_reset["tool_approvals"]["total"] == 1
    assert pre_reset["fallback_rates"]["sdk_to_raw"]["attempts"] == 1

    reset_observability_metrics()
    post_reset = get_observability_metrics().snapshot()
    assert post_reset["requests"]["total"] == 0
    assert post_reset["tool_approvals"]["total"] == 0
    assert post_reset["fallback_rates"] == {}
