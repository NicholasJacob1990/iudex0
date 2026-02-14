from app.services.ai.shared.quotas import TenantQuotaManager


def test_request_quota_blocks_after_limit():
    quota = TenantQuotaManager(
        max_requests_per_window=2,
        max_delegated_tokens_per_window=1000,
        window_seconds=60,
    )

    d1 = quota.check_and_consume("tenant-1", requests_cost=1)
    d2 = quota.check_and_consume("tenant-1", requests_cost=1)
    d3 = quota.check_and_consume("tenant-1", requests_cost=1)

    assert d1.allowed is True
    assert d2.allowed is True
    assert d3.allowed is False
    assert d3.reason == "requests_per_window_exceeded"


def test_token_quota_blocks_after_limit():
    quota = TenantQuotaManager(
        max_requests_per_window=100,
        max_delegated_tokens_per_window=100,
        window_seconds=60,
    )

    d1 = quota.check_and_consume("tenant-2", delegated_tokens_cost=70)
    d2 = quota.check_and_consume("tenant-2", delegated_tokens_cost=31)

    assert d1.allowed is True
    assert d2.allowed is False
    assert d2.reason == "delegated_tokens_per_window_exceeded"


def test_quota_window_resets_with_time():
    now = {"t": 0.0}
    quota = TenantQuotaManager(
        max_requests_per_window=1,
        max_delegated_tokens_per_window=1000,
        window_seconds=60,
        clock=lambda: now["t"],
    )

    first = quota.check_and_consume("tenant-3")
    blocked = quota.check_and_consume("tenant-3")
    now["t"] = 61.0
    reset = quota.check_and_consume("tenant-3")

    assert first.allowed is True
    assert blocked.allowed is False
    assert reset.allowed is True


def test_subagent_concurrency_slots():
    quota = TenantQuotaManager(
        max_requests_per_window=100,
        max_delegated_tokens_per_window=10000,
        max_concurrent_subagents=2,
        window_seconds=60,
    )

    assert quota.acquire_subagent_slot("tenant-4") is True
    assert quota.acquire_subagent_slot("tenant-4") is True
    assert quota.acquire_subagent_slot("tenant-4") is False
    quota.release_subagent_slot("tenant-4")
    assert quota.acquire_subagent_slot("tenant-4") is True

