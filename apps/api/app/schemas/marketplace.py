"""Pydantic schemas for marketplace."""
from typing import Optional
from pydantic import BaseModel, Field


class MarketplacePublish(BaseModel):
    resource_type: str = Field(..., description="library_item, workflow, librarian")
    resource_id: str
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    category: str = "minutas"
    tags: list[str] = []


class MarketplaceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


class MarketplaceReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class MarketplaceItemResponse(BaseModel):
    id: str
    publisher_id: str
    publisher_name: Optional[str] = None
    resource_type: str
    resource_id: str
    title: str
    description: Optional[str]
    category: str
    tags: list[str]
    download_count: int
    avg_rating: float
    rating_count: int
    preview_data: Optional[dict] = None
    created_at: str

    class Config:
        from_attributes = True
