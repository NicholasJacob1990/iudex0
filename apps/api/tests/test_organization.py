"""
Tests for Multi-tenancy: Organization, Members, Teams, OrgContext.

Tests:
- Organization model and slug generation
- OrganizationMember roles and constraints
- Team creation and membership
- OrgContext dataclass and properties
- require_org_role dependency
- JWT org_id inclusion
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.models.organization import (
    Organization,
    OrganizationMember,
    OrgRole,
    Team,
    TeamMember,
    _slugify,
)


# =============================================================================
# TestSlugify
# =============================================================================

class TestSlugify:
    """Test slug generation helper."""

    def test_simple_name(self):
        slug = _slugify("Silva & Associados")
        assert "silva" in slug
        assert slug.isascii()
        assert " " not in slug

    def test_accented_name(self):
        slug = _slugify("Escritório Jurídico São Paulo")
        assert "escritorio" in slug
        assert "sao" in slug

    def test_empty_string(self):
        assert _slugify("") == "org"

    def test_special_chars_only(self):
        assert _slugify("!@#$%") == "org"

    def test_long_name_truncated(self):
        slug = _slugify("A" * 200)
        assert len(slug) <= 100


# =============================================================================
# TestOrganizationModel
# =============================================================================

class TestOrganizationModel:
    """Test Organization model."""

    def test_create_organization(self):
        org = Organization(
            id="org-1",
            name="Escritório Silva",
            slug="escritorio-silva",
        )
        assert org.id == "org-1"
        assert org.name == "Escritório Silva"
        assert org.slug == "escritorio-silva"
        assert repr(org) == "<Organization(id=org-1, name=Escritório Silva, slug=escritorio-silva)>"

    def test_organization_defaults(self):
        """SQLAlchemy defaults apply on INSERT, not on Python instantiation.
        Here we just verify the model can be created without errors."""
        org = Organization(
            id="org-2",
            name="Test",
            slug="test",
            plan="PROFESSIONAL",
            max_members=10,
            is_active=True,
        )
        assert org.plan == "PROFESSIONAL"
        assert org.max_members == 10
        assert org.is_active is True

    def test_generate_slug(self):
        slug = Organization.generate_slug("Escritório Silva & Associados")
        assert isinstance(slug, str)
        assert len(slug) > 0
        # Should be URL-safe
        assert " " not in slug


# =============================================================================
# TestOrgRole
# =============================================================================

class TestOrgRole:
    """Test OrgRole enum."""

    def test_enum_values(self):
        assert OrgRole.ADMIN.value == "admin"
        assert OrgRole.ADVOGADO.value == "advogado"
        assert OrgRole.ESTAGIARIO.value == "estagiario"

    def test_string_comparison(self):
        assert OrgRole.ADMIN == "admin"
        assert OrgRole.ADVOGADO != "admin"


# =============================================================================
# TestOrganizationMember
# =============================================================================

class TestOrganizationMember:
    """Test OrganizationMember model."""

    def test_create_member(self):
        member = OrganizationMember(
            id="mem-1",
            organization_id="org-1",
            user_id="user-1",
            role=OrgRole.ADMIN,
            is_active=True,
        )
        assert member.organization_id == "org-1"
        assert member.user_id == "user-1"
        assert member.role == OrgRole.ADMIN
        assert member.is_active is True

    def test_default_role(self):
        """SQLAlchemy defaults apply on INSERT. Verify enum is assignable."""
        member = OrganizationMember(
            id="mem-2",
            organization_id="org-1",
            user_id="user-2",
            role=OrgRole.ADVOGADO,
        )
        assert member.role == OrgRole.ADVOGADO

    def test_roles_assignable(self):
        for role in [OrgRole.ADMIN, OrgRole.ADVOGADO, OrgRole.ESTAGIARIO]:
            member = OrganizationMember(
                id=f"mem-{role.value}",
                organization_id="org-1",
                user_id=f"user-{role.value}",
                role=role,
            )
            assert member.role == role

    def test_repr(self):
        member = OrganizationMember(
            id="mem-1",
            organization_id="org-1",
            user_id="user-1",
            role=OrgRole.ADMIN,
        )
        r = repr(member)
        assert "org-1" in r
        assert "user-1" in r


# =============================================================================
# TestTeam
# =============================================================================

class TestTeam:
    """Test Team model."""

    def test_create_team(self):
        team = Team(
            id="team-1",
            organization_id="org-1",
            name="Contencioso",
            description="Equipe de contencioso cível",
        )
        assert team.id == "team-1"
        assert team.organization_id == "org-1"
        assert team.name == "Contencioso"

    def test_team_without_description(self):
        team = Team(
            id="team-2",
            organization_id="org-1",
            name="Consultivo",
        )
        assert team.description is None


# =============================================================================
# TestTeamMember
# =============================================================================

class TestTeamMember:
    """Test TeamMember model."""

    def test_create_team_member(self):
        tm = TeamMember(
            id="tm-1",
            team_id="team-1",
            user_id="user-1",
        )
        assert tm.team_id == "team-1"
        assert tm.user_id == "user-1"


# =============================================================================
# TestOrgContext
# =============================================================================

class TestOrgContext:
    """Test OrgContext dataclass."""

    def test_single_user_mode(self):
        from app.core.security import OrgContext

        mock_user = MagicMock()
        mock_user.id = "user-123"

        ctx = OrgContext(user=mock_user)
        assert ctx.organization_id is None
        assert ctx.org_role is None
        assert ctx.team_ids == []
        assert ctx.is_org_member is False
        assert ctx.is_org_admin is False
        assert ctx.tenant_id == "user-123"

    def test_org_member_mode(self):
        from app.core.security import OrgContext

        mock_user = MagicMock()
        mock_user.id = "user-456"

        ctx = OrgContext(
            user=mock_user,
            organization_id="org-789",
            org_role="advogado",
            team_ids=["team-1", "team-2"],
        )
        assert ctx.is_org_member is True
        assert ctx.is_org_admin is False
        assert ctx.tenant_id == "org-789"
        assert len(ctx.team_ids) == 2

    def test_org_admin(self):
        from app.core.security import OrgContext

        mock_user = MagicMock()
        mock_user.id = "user-admin"

        ctx = OrgContext(
            user=mock_user,
            organization_id="org-1",
            org_role="admin",
        )
        assert ctx.is_org_admin is True
        assert ctx.is_org_member is True

    def test_tenant_id_fallback(self):
        from app.core.security import OrgContext

        mock_user = MagicMock()
        mock_user.id = "user-solo"

        ctx = OrgContext(user=mock_user, organization_id=None)
        assert ctx.tenant_id == "user-solo"

        ctx2 = OrgContext(user=mock_user, organization_id="org-abc")
        assert ctx2.tenant_id == "org-abc"


# =============================================================================
# TestRequireOrgRole
# =============================================================================

class TestRequireOrgRole:
    """Test require_org_role dependency factory."""

    @pytest.mark.asyncio
    async def test_allows_valid_role(self):
        from app.core.security import OrgContext, require_org_role
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-1"

        ctx = OrgContext(
            user=mock_user,
            organization_id="org-1",
            org_role="admin",
        )

        checker = require_org_role("admin", "advogado")
        # Inject ctx directly by calling the inner function
        # The dependency expects OrgContext
        result = await checker(ctx=ctx)
        assert result.is_org_admin is True

    @pytest.mark.asyncio
    async def test_denies_wrong_role(self):
        from app.core.security import OrgContext, require_org_role
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-1"

        ctx = OrgContext(
            user=mock_user,
            organization_id="org-1",
            org_role="estagiario",
        )

        checker = require_org_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            await checker(ctx=ctx)
        assert exc_info.value.status_code == 403
        assert "Permissão insuficiente" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_denies_no_org(self):
        from app.core.security import OrgContext, require_org_role
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "user-1"

        ctx = OrgContext(user=mock_user)  # No org

        checker = require_org_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            await checker(ctx=ctx)
        assert exc_info.value.status_code == 403
        assert "Requer membro" in exc_info.value.detail


# =============================================================================
# TestJWTOrgContext
# =============================================================================

class TestJWTOrgContext:
    """Test JWT payload includes org_id."""

    def test_jwt_with_org_id(self):
        from app.core.security import create_access_token, decode_token

        token = create_access_token(
            data={
                "sub": "user-1",
                "type": "access",
                "role": "USER",
                "plan": "FREE",
                "org_id": "org-abc",
            }
        )
        payload = decode_token(token)
        assert payload["org_id"] == "org-abc"
        assert payload["sub"] == "user-1"

    def test_jwt_without_org_id(self):
        from app.core.security import create_access_token, decode_token

        token = create_access_token(
            data={
                "sub": "user-2",
                "type": "access",
                "role": "USER",
                "plan": "FREE",
                "org_id": None,
            }
        )
        payload = decode_token(token)
        assert payload["org_id"] is None
        assert payload["sub"] == "user-2"

    def test_jwt_backwards_compat(self):
        """Token sem org_id (legado) deve funcionar."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(
            data={
                "sub": "user-3",
                "type": "access",
                "role": "USER",
                "plan": "FREE",
            }
        )
        payload = decode_token(token)
        assert payload["sub"] == "user-3"
        # org_id not present — should not error
        assert payload.get("org_id") is None


# =============================================================================
# TestSchemas
# =============================================================================

class TestSchemas:
    """Test Pydantic schemas validation."""

    def test_org_create_valid(self):
        from app.schemas.organization import OrgCreate

        data = OrgCreate(name="Escritório Silva", cnpj="12.345.678/0001-90")
        assert data.name == "Escritório Silva"
        assert data.cnpj == "12.345.678/0001-90"

    def test_org_create_name_too_short(self):
        from app.schemas.organization import OrgCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OrgCreate(name="A")

    def test_invite_request_valid(self):
        from app.schemas.organization import InviteRequest

        data = InviteRequest(email="joao@escritorio.com", role="advogado")
        assert data.email == "joao@escritorio.com"
        assert data.role == "advogado"

    def test_invite_request_invalid_role(self):
        from app.schemas.organization import InviteRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InviteRequest(email="joao@escritorio.com", role="superadmin")

    def test_role_update_valid(self):
        from app.schemas.organization import RoleUpdate

        data = RoleUpdate(role="estagiario")
        assert data.role == "estagiario"

    def test_team_create_valid(self):
        from app.schemas.organization import TeamCreate

        data = TeamCreate(name="Contencioso", description="Equipe cível")
        assert data.name == "Contencioso"

    def test_org_response_serialization(self):
        from app.schemas.organization import OrgResponse
        from datetime import datetime

        resp = OrgResponse(
            id="org-1",
            name="Test Org",
            slug="test-org",
            plan="PROFESSIONAL",
            max_members=10,
            member_count=3,
            is_active=True,
            created_at=datetime(2026, 1, 28),
            updated_at=datetime(2026, 1, 28),
        )
        d = resp.model_dump()
        assert d["id"] == "org-1"
        assert d["member_count"] == 3
        assert d["slug"] == "test-org"
