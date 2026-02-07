import pytest

from app.services.ai.shared.feature_flags import FeatureFlagManager


@pytest.fixture(autouse=True)
def _reset_runtime_overrides():
    FeatureFlagManager.clear_runtime_overrides()
    yield
    FeatureFlagManager.clear_runtime_overrides()


def test_global_kill_switch_disables_all_executors():
    flags = FeatureFlagManager(
        env={
            "IUDEX_AGENTIC_GLOBAL_ENABLED": "false",
            "IUDEX_AGENTIC_EXECUTOR_CLAUDE_AGENT_ENABLED": "true",
            "IUDEX_AGENTIC_EXECUTOR_OPENAI_AGENT_ENABLED": "true",
            "IUDEX_AGENTIC_EXECUTOR_GOOGLE_AGENT_ENABLED": "true",
            "IUDEX_AGENTIC_EXECUTOR_LANGGRAPH_ENABLED": "true",
        },
        sdk_detector=lambda: True,
    )

    assert flags.is_executor_enabled("claude_agent") is False
    assert flags.is_executor_enabled("openai_agent") is False
    assert flags.is_executor_enabled("google_agent") is False
    assert flags.is_executor_enabled("langgraph") is False


def test_claude_executor_can_enforce_sdk_autodetect():
    flags = FeatureFlagManager(
        env={
            "IUDEX_AGENTIC_GLOBAL_ENABLED": "true",
            "IUDEX_AGENTIC_EXECUTOR_CLAUDE_AGENT_ENABLED": "true",
            "IUDEX_AGENTIC_ENFORCE_SDK_AVAILABILITY": "true",
            "IUDEX_AGENTIC_AUTO_DETECT_SDK": "true",
        },
        sdk_detector=lambda: False,
    )

    assert flags.is_sdk_available() is False
    assert flags.is_executor_enabled("claude_agent") is False


def test_canary_rollout_is_deterministic():
    flags = FeatureFlagManager(
        env={"IUDEX_AGENTIC_CANARY_PERCENT": "20"},
        sdk_detector=lambda: True,
    )

    result1 = flags.is_canary_enabled("tenant-alpha")
    result2 = flags.is_canary_enabled("tenant-alpha")
    result3 = flags.is_canary_enabled("tenant-beta")

    assert result1 == result2
    assert isinstance(result3, bool)


def test_tool_safety_limits_are_clamped():
    flags = FeatureFlagManager(
        env={
            "IUDEX_AGENTIC_MAX_TOOL_CALLS": "9999",
            "IUDEX_AGENTIC_MAX_DELEGATED_TOKENS": "10",
        },
        sdk_detector=lambda: True,
    )
    limits = flags.get_tool_safety_limits()

    assert limits.max_tool_calls_per_request == 200
    assert limits.max_delegated_tokens_per_request == 1000


def test_runtime_override_applies_for_default_env_only():
    FeatureFlagManager.set_runtime_override("IUDEX_AGENTIC_GLOBAL_ENABLED", False)

    flags_with_default_env = FeatureFlagManager(sdk_detector=lambda: True)
    assert flags_with_default_env.is_global_enabled() is False

    flags_with_custom_env = FeatureFlagManager(
        env={"IUDEX_AGENTIC_GLOBAL_ENABLED": "true"},
        sdk_detector=lambda: True,
    )
    assert flags_with_custom_env.is_global_enabled() is True
