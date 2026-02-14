"""
Admin endpoints for feature flag management.

Protected by require_role("admin").
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import require_role
from app.models.user import User
from app.services.ai.shared.feature_flags import FeatureFlagManager

router = APIRouter()

_manager = FeatureFlagManager()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FeatureFlagSnapshotResponse(BaseModel):
    global_enabled: bool
    auto_detect_sdk: bool
    sdk_available: bool
    canary_percent: int
    analytics_sample_rate: float
    executor_enabled: Dict[str, bool]
    limits: Dict[str, int]
    runtime_overrides: Dict[str, str]


class SetOverrideRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Feature flag key (must start with IUDEX_AGENTIC_ or be QUICK_AGENT_BRIDGE_ENABLED)")
    value: str = Field(..., description="Value to set (true/false, or numeric)")


class SetOverrideResponse(BaseModel):
    key: str
    value: str
    success: bool


class RemoveOverrideRequest(BaseModel):
    key: str = Field(..., min_length=1)


class RemoveOverrideResponse(BaseModel):
    key: str
    removed: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/admin/feature-flags",
    response_model=FeatureFlagSnapshotResponse,
    summary="Get current feature flags snapshot",
)
async def get_feature_flags(
    current_user: User = Depends(require_role("admin")),
) -> FeatureFlagSnapshotResponse:
    """Return the current state of all agentic feature flags."""
    snap = _manager.snapshot()
    return FeatureFlagSnapshotResponse(
        global_enabled=snap.global_enabled,
        auto_detect_sdk=snap.auto_detect_sdk,
        sdk_available=snap.sdk_available,
        canary_percent=snap.canary_percent,
        analytics_sample_rate=snap.analytics_sample_rate,
        executor_enabled=snap.executor_enabled,
        limits={
            "max_tool_calls_per_request": snap.limits.max_tool_calls_per_request,
            "max_delegated_tokens_per_request": snap.limits.max_delegated_tokens_per_request,
        },
        runtime_overrides=FeatureFlagManager.runtime_overrides(),
    )


@router.post(
    "/admin/feature-flags/override",
    response_model=SetOverrideResponse,
    summary="Set a runtime feature flag override",
)
async def set_feature_flag_override(
    request: SetOverrideRequest,
    current_user: User = Depends(require_role("admin")),
) -> SetOverrideResponse:
    """Set a runtime override for a feature flag. Changes take effect immediately."""
    try:
        FeatureFlagManager.set_runtime_override(request.key, request.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SetOverrideResponse(key=request.key, value=request.value, success=True)


@router.delete(
    "/admin/feature-flags/override",
    response_model=RemoveOverrideResponse,
    summary="Remove a runtime feature flag override",
)
async def remove_feature_flag_override(
    request: RemoveOverrideRequest,
    current_user: User = Depends(require_role("admin")),
) -> RemoveOverrideResponse:
    """Remove a runtime override, reverting to the environment variable value."""
    removed = FeatureFlagManager.remove_runtime_override(request.key)
    return RemoveOverrideResponse(key=request.key, removed=removed)


@router.post(
    "/admin/feature-flags/clear-overrides",
    summary="Clear all runtime feature flag overrides",
)
async def clear_feature_flag_overrides(
    current_user: User = Depends(require_role("admin")),
) -> Dict[str, Any]:
    """Clear all runtime overrides, reverting everything to environment variable values."""
    FeatureFlagManager.clear_runtime_overrides()
    return {"cleared": True}
