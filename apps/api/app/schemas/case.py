from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class CaseStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"

class CaseBase(BaseModel):
    title: str
    client_name: Optional[str] = None
    process_number: Optional[str] = None
    court: Optional[str] = None
    area: Optional[str] = None
    description: Optional[str] = None
    thesis: Optional[str] = None
    status: CaseStatus = CaseStatus.ACTIVE

class CaseCreate(CaseBase):
    pass

class CaseUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    process_number: Optional[str] = None
    court: Optional[str] = None
    area: Optional[str] = None
    description: Optional[str] = None
    thesis: Optional[str] = None
    status: Optional[CaseStatus] = None

class CaseResponse(CaseBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
