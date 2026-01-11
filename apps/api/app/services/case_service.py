from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.case import Case
from app.schemas.case import CaseCreate, CaseUpdate
from app.models.user import User

class CaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_cases(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Case]:
        query = select(Case).where(Case.user_id == user_id).order_by(desc(Case.updated_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_case(self, case_id: str, user_id: str) -> Optional[Case]:
        query = select(Case).where(Case.id == case_id, Case.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_case(self, case_in: CaseCreate, user_id: str) -> Case:
        db_case = Case(
            **case_in.model_dump(),
            user_id=user_id
        )
        self.db.add(db_case)
        await self.db.commit()
        await self.db.refresh(db_case)
        return db_case

    async def update_case(self, case_id: str, case_in: CaseUpdate, user_id: str) -> Optional[Case]:
        case = await self.get_case(case_id, user_id)
        if not case:
            return None
        
        update_data = case_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(case, field, value)
            
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def delete_case(self, case_id: str, user_id: str) -> bool:
        case = await self.get_case(case_id, user_id)
        if not case:
            return False
            
        await self.db.delete(case)
        await self.db.commit()
        return True
