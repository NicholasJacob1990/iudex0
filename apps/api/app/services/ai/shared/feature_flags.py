from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata as importlib_metadata
from typing import Callable, Mapping, Optional
import os
from threading import RLock


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _as_float(value: object, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _anthropic_version_at_least(required: tuple[int, int, int]) -> bool:
    try:
        version = importlib_metadata.version("anthropic")
    except Exception:
        return False
    parts = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]) >= required


@dataclass(frozen=True)
class ToolSafetyLimits:
    max_tool_calls_per_request: int
    max_delegated_tokens_per_request: int


@dataclass(frozen=True)
class FeatureFlagSnapshot:
    global_enabled: bool
    auto_detect_sdk: bool
    sdk_available: bool
    canary_percent: int
    analytics_sample_rate: float
    executor_enabled: dict[str, bool]
    limits: ToolSafetyLimits


class FeatureFlagManager:
    """
    Feature flags em camadas para execução agentic.

    Camadas:
    1) kill switch global
    2) auto-detecção de SDK (Claude)
    3) enable por executor/nó
    4) limites de segurança (tool calls / tokens delegados)
    5) amostragem de analytics + canary percentual
    """

    _EXECUTORS = ("claude_agent", "openai_agent", "google_agent", "langgraph", "parallel")
    _OVERRIDES_LOCK = RLock()
    _RUNTIME_OVERRIDES: dict[str, str] = {}

    def __init__(
        self,
        env: Optional[Mapping[str, str]] = None,
        *,
        sdk_detector: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._env = env if env is not None else os.environ
        self._use_runtime_overrides = env is None
        self._sdk_detector = sdk_detector or (lambda: _anthropic_version_at_least((0, 50, 0)))

    @classmethod
    def _normalize_override_value(cls, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @classmethod
    def _is_allowed_override_key(cls, key: str) -> bool:
        normalized = str(key or "").strip().upper()
        return (
            normalized == "QUICK_AGENT_BRIDGE_ENABLED"
            or normalized.startswith("IUDEX_AGENTIC_")
        )

    @classmethod
    def set_runtime_override(cls, key: str, value: object) -> None:
        normalized_key = str(key or "").strip().upper()
        if not cls._is_allowed_override_key(normalized_key):
            raise ValueError(f"Feature flag key não suportada: {key}")
        with cls._OVERRIDES_LOCK:
            cls._RUNTIME_OVERRIDES[normalized_key] = cls._normalize_override_value(value)

    @classmethod
    def remove_runtime_override(cls, key: str) -> bool:
        normalized_key = str(key or "").strip().upper()
        with cls._OVERRIDES_LOCK:
            if normalized_key in cls._RUNTIME_OVERRIDES:
                del cls._RUNTIME_OVERRIDES[normalized_key]
                return True
        return False

    @classmethod
    def clear_runtime_overrides(cls) -> None:
        with cls._OVERRIDES_LOCK:
            cls._RUNTIME_OVERRIDES.clear()

    @classmethod
    def runtime_overrides(cls) -> dict[str, str]:
        with cls._OVERRIDES_LOCK:
            return dict(cls._RUNTIME_OVERRIDES)

    def _env_get(self, key: str) -> Optional[str]:
        if self._use_runtime_overrides:
            overrides = self.runtime_overrides()
            if key in overrides:
                return overrides[key]
        return self._env.get(key)

    def _env_bool(self, key: str, default: bool) -> bool:
        return _as_bool(self._env_get(key), default)

    def _env_int(self, key: str, default: int, *, minimum: int, maximum: int) -> int:
        return _as_int(self._env_get(key), default, minimum=minimum, maximum=maximum)

    def _env_float(self, key: str, default: float, *, minimum: float, maximum: float) -> float:
        return _as_float(self._env_get(key), default, minimum=minimum, maximum=maximum)

    def is_global_enabled(self) -> bool:
        return self._env_bool("IUDEX_AGENTIC_GLOBAL_ENABLED", True)

    def is_auto_detect_enabled(self) -> bool:
        return self._env_bool("IUDEX_AGENTIC_AUTO_DETECT_SDK", True)

    def is_sdk_available(self) -> bool:
        if not self.is_auto_detect_enabled():
            return self._env_bool("IUDEX_AGENTIC_SDK_AVAILABLE", True)
        return bool(self._sdk_detector())

    def is_executor_enabled(self, executor_name: str) -> bool:
        name = str(executor_name or "").strip().lower()
        if name not in self._EXECUTORS:
            return False
        if not self.is_global_enabled():
            return False
        env_key = f"IUDEX_AGENTIC_EXECUTOR_{name.upper()}_ENABLED"
        enabled = self._env_bool(env_key, True)
        if not enabled:
            return False
        if name == "claude_agent":
            enforce_sdk = self._env_bool("IUDEX_AGENTIC_ENFORCE_SDK_AVAILABILITY", False)
            if enforce_sdk and not self.is_sdk_available():
                return False
        return True

    def is_canary_enabled(self, actor_id: Optional[str]) -> bool:
        percent = self._env_int("IUDEX_AGENTIC_CANARY_PERCENT", 100, minimum=0, maximum=100)
        if percent >= 100:
            return True
        if percent <= 0:
            return False
        if not actor_id:
            return False
        bucket = int(sha256(actor_id.encode("utf-8")).hexdigest()[:8], 16) % 100
        return bucket < percent

    def get_tool_safety_limits(self) -> ToolSafetyLimits:
        return ToolSafetyLimits(
            max_tool_calls_per_request=self._env_int(
                "IUDEX_AGENTIC_MAX_TOOL_CALLS",
                30,
                minimum=1,
                maximum=200,
            ),
            max_delegated_tokens_per_request=self._env_int(
                "IUDEX_AGENTIC_MAX_DELEGATED_TOKENS",
                80_000,
                minimum=1_000,
                maximum=2_000_000,
            ),
        )

    def analytics_sample_rate(self) -> float:
        return self._env_float(
            "IUDEX_AGENTIC_ANALYTICS_SAMPLE_RATE",
            1.0,
            minimum=0.0,
            maximum=1.0,
        )

    def quick_agent_bridge_enabled(self) -> bool:
        legacy_default = self._env_bool("QUICK_AGENT_BRIDGE_ENABLED", False)
        return self._env_bool("IUDEX_AGENTIC_QUICK_BRIDGE_ENABLED", legacy_default)

    def snapshot(self) -> FeatureFlagSnapshot:
        return FeatureFlagSnapshot(
            global_enabled=self.is_global_enabled(),
            auto_detect_sdk=self.is_auto_detect_enabled(),
            sdk_available=self.is_sdk_available(),
            canary_percent=self._env_int("IUDEX_AGENTIC_CANARY_PERCENT", 100, minimum=0, maximum=100),
            analytics_sample_rate=self.analytics_sample_rate(),
            executor_enabled={name: self.is_executor_enabled(name) for name in self._EXECUTORS},
            limits=self.get_tool_safety_limits(),
        )
