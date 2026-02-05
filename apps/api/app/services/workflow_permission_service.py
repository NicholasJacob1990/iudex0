"""
Workflow Permission Service — Centralized permission checks.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow
from app.models.workflow_permission import (
    WorkflowPermission,
    WorkflowBuilderRole,
    BuildAccess,
    RunAccess,
)
from app.models.organization import OrganizationMember


class WorkflowPermissionService:
    """Handles all permission checks for workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_org_workflow_role(self, user_id: str, org_id: Optional[str]) -> Optional[str]:
        """Get user's workflow role from organization membership."""
        if not org_id:
            return None
        stmt = select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == org_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()
        if not member:
            return None
        return getattr(member, 'workflow_role', None)

    async def _get_workflow_permission(self, workflow_id: str, user_id: str) -> Optional[WorkflowPermission]:
        """Get per-workflow permission for a user."""
        stmt = select(WorkflowPermission).where(
            WorkflowPermission.workflow_id == workflow_id,
            WorkflowPermission.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def can_build(self, user_id: str, workflow: Workflow) -> bool:
        """Check if user can edit the workflow."""
        # Owner always can build
        if workflow.user_id == user_id:
            return True
        # Check org role
        org_role = await self._get_org_workflow_role(user_id, workflow.organization_id)
        if org_role == WorkflowBuilderRole.WORKFLOW_ADMIN.value:
            return True
        # Check per-workflow permission
        perm = await self._get_workflow_permission(workflow.id, user_id)
        if perm and perm.build_access in (BuildAccess.EDIT, BuildAccess.FULL):
            return True
        return False

    async def can_run(self, user_id: str, workflow: Workflow) -> bool:
        """Check if user can execute the workflow."""
        # Owner always can run
        if workflow.user_id == user_id:
            return True
        # Check org role (admin and builder can run)
        org_role = await self._get_org_workflow_role(user_id, workflow.organization_id)
        if org_role in (
            WorkflowBuilderRole.WORKFLOW_ADMIN.value,
            WorkflowBuilderRole.WORKFLOW_BUILDER.value,
        ):
            return True
        # Check per-workflow permission
        perm = await self._get_workflow_permission(workflow.id, user_id)
        if perm and perm.run_access == RunAccess.RUN:
            return True
        return False

    async def can_approve(self, user_id: str, workflow: Workflow) -> bool:
        """Check if user can approve/reject the workflow."""
        if workflow.user_id == user_id:
            return False  # Can't approve own workflow
        org_role = await self._get_org_workflow_role(user_id, workflow.organization_id)
        return org_role == WorkflowBuilderRole.WORKFLOW_ADMIN.value

    async def can_publish(self, user_id: str, workflow: Workflow) -> bool:
        """Check if user can publish the workflow."""
        if workflow.user_id == user_id:
            return True
        org_role = await self._get_org_workflow_role(user_id, workflow.organization_id)
        return org_role == WorkflowBuilderRole.WORKFLOW_ADMIN.value

    async def grant_access(
        self,
        workflow_id: str,
        user_id: str,
        granted_by: str,
        build: BuildAccess = BuildAccess.NONE,
        run: RunAccess = RunAccess.NONE,
    ) -> WorkflowPermission:
        """Grant or update permission for a user on a workflow."""
        perm = await self._get_workflow_permission(workflow_id, user_id)
        if perm:
            perm.build_access = build
            perm.run_access = run
        else:
            perm = WorkflowPermission(
                id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                user_id=user_id,
                build_access=build,
                run_access=run,
                granted_by=granted_by,
            )
            self.db.add(perm)
        await self.db.flush()
        return perm

    async def revoke_access(self, workflow_id: str, user_id: str) -> bool:
        """Revoke all permissions for a user on a workflow."""
        perm = await self._get_workflow_permission(workflow_id, user_id)
        if perm:
            await self.db.delete(perm)
            await self.db.flush()
            return True
        return False

    async def list_permissions(self, workflow_id: str) -> list:
        """List all permissions for a workflow."""
        stmt = select(WorkflowPermission).where(
            WorkflowPermission.workflow_id == workflow_id
        )
        result = await self.db.execute(stmt)
        return [p.to_dict() for p in result.scalars().all()]
