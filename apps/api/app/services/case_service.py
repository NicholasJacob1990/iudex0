from typing import List, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.case import Case
from app.schemas.case import CaseCreate, CaseUpdate
from app.models.user import User
from app.core.security import OrgContext, build_tenant_filter


class CaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _tenant_filter(self, ctx_or_uid: Union[OrgContext, str]):
        """Retorna cláusula WHERE para isolamento de tenant."""
        if isinstance(ctx_or_uid, OrgContext):
            return build_tenant_filter(ctx_or_uid, Case)
        return Case.user_id == ctx_or_uid

    async def get_cases(self, ctx_or_uid: Union[OrgContext, str], skip: int = 0, limit: int = 100) -> List[Case]:
        query = (
            select(Case)
            .where(self._tenant_filter(ctx_or_uid))
            .order_by(desc(Case.updated_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_case(self, case_id: str, ctx_or_uid: Union[OrgContext, str]) -> Optional[Case]:
        query = select(Case).where(Case.id == case_id, self._tenant_filter(ctx_or_uid))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_case(self, case_in: CaseCreate, ctx_or_uid: Union[OrgContext, str]) -> Case:
        if isinstance(ctx_or_uid, OrgContext):
            user_id = ctx_or_uid.user.id
            org_id = ctx_or_uid.organization_id
        else:
            user_id = ctx_or_uid
            org_id = None

        db_case = Case(
            **case_in.model_dump(),
            user_id=user_id,
            organization_id=org_id,
        )
        self.db.add(db_case)
        await self.db.commit()
        await self.db.refresh(db_case)
        return db_case

    async def update_case(self, case_id: str, case_in: CaseUpdate, ctx_or_uid: Union[OrgContext, str]) -> Optional[Case]:
        case = await self.get_case(case_id, ctx_or_uid)
        if not case:
            return None

        update_data = case_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(case, field, value)

        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def delete_case(self, case_id: str, ctx_or_uid: Union[OrgContext, str]) -> bool:
        case = await self.get_case(case_id, ctx_or_uid)
        if not case:
            return False

        await self.db.delete(case)
        await self.db.commit()
        return True
