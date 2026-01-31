"""add_multi_tenancy

Revision ID: g7h8i9j0k1l2
Revises: f6c7d8e9a0b1
Create Date: 2026-01-28 12:00:00

Adds:
- organizations: Tabela de organizações (escritórios)
- organization_members: Vínculo user-org com role
- teams: Equipes dentro de organizações
- team_members: Vínculo user-team
- organization_id nullable em users, cases, chats, documents
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6c7d8e9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # ===== ORGANIZATIONS TABLE =====
    if "organizations" not in existing_tables:
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("slug", sa.String(100), unique=True, nullable=False),
            sa.Column("cnpj", sa.String(18), nullable=True),
            sa.Column("oab_section", sa.String(10), nullable=True),
            sa.Column("plan", sa.String(20), nullable=False, server_default="PROFESSIONAL"),
            sa.Column("max_members", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_organizations_slug", "organizations", ["slug"], unique=True)

    # ===== ORGANIZATION_MEMBERS TABLE =====
    if "organization_members" not in existing_tables:
        op.create_table(
            "organization_members",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="advogado"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
        )
        op.create_index("idx_org_member_org", "organization_members", ["organization_id"])
        op.create_index("idx_org_member_user", "organization_members", ["user_id"])
        op.create_index("idx_org_member_lookup", "organization_members", ["organization_id", "user_id"])

    # ===== TEAMS TABLE =====
    if "teams" not in existing_tables:
        op.create_table(
            "teams",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("organization_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_teams_org", "teams", ["organization_id"])

    # ===== TEAM_MEMBERS TABLE =====
    if "team_members" not in existing_tables:
        op.create_table(
            "team_members",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("team_id", sa.String(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        )
        op.create_index("idx_team_member_team", "team_members", ["team_id"])
        op.create_index("idx_team_member_user", "team_members", ["user_id"])

    # ===== ADD organization_id TO EXISTING TABLES =====
    # Nullable columns — zero impact on existing data

    for table_name in ["users", "cases", "chats", "documents"]:
        existing_columns = [c["name"] for c in inspector.get_columns(table_name)]
        if "organization_id" not in existing_columns:
            op.add_column(
                table_name,
                sa.Column("organization_id", sa.String(), nullable=True),
            )
            # FK constraint (skip for SQLite which has limited ALTER TABLE support)
            dialect = bind.dialect.name
            if dialect != "sqlite":
                op.create_foreign_key(
                    f"fk_{table_name}_org",
                    table_name,
                    "organizations",
                    ["organization_id"],
                    ["id"],
                )
            op.create_index(f"idx_{table_name}_org_id", table_name, ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Remove organization_id columns
    for table_name in ["documents", "chats", "cases", "users"]:
        try:
            op.drop_index(f"idx_{table_name}_org_id", table_name=table_name)
        except Exception:
            pass
        if dialect != "sqlite":
            try:
                op.drop_constraint(f"fk_{table_name}_org", table_name, type_="foreignkey")
            except Exception:
                pass
        try:
            op.drop_column(table_name, "organization_id")
        except Exception:
            pass

    # Drop tables in reverse order
    for table_name in ["team_members", "teams", "organization_members", "organizations"]:
        try:
            op.drop_table(table_name)
        except Exception:
            pass
