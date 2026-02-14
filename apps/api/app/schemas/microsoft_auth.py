"""Schemas for Microsoft SSO authentication."""

from typing import Optional
from pydantic import BaseModel, Field


class MicrosoftSSORequest(BaseModel):
    microsoft_token: str = Field(..., description="JWT token from Microsoft NAA/SSO")
    source: Optional[str] = Field(None, description="Source: 'outlook-addin' | 'teams-tab'")


class TeamsSSORequest(BaseModel):
    teams_token: str = Field(..., description="JWT token from Teams SSO")


class MicrosoftSSOResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
