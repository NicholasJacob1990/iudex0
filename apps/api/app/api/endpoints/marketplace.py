"""Marketplace endpoints for discovering and sharing resources."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.marketplace import MarketplaceItem, MarketplaceReview, MarketplaceCategory
from app.schemas.marketplace import (
    MarketplacePublish, MarketplaceUpdate,
    MarketplaceReviewCreate, MarketplaceItemResponse,
)

router = APIRouter()


@router.get("")
async def list_marketplace(
    category: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    sort: str = Query("popular", description="popular, recent, rating"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Browse public marketplace items."""
    query = select(MarketplaceItem).where(MarketplaceItem.is_published == True)

    if category:
        query = query.where(MarketplaceItem.category == category)

    if search:
        # Escapar caracteres especiais de LIKE para evitar wildcard injection
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_search}%"
        query = query.where(
            MarketplaceItem.title.ilike(pattern)
            | MarketplaceItem.description.ilike(pattern)
        )

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        for tag in tag_list:
            query = query.where(MarketplaceItem.tags.contains([tag]))

    # Sorting
    if sort == "popular":
        query = query.order_by(desc(MarketplaceItem.download_count))
    elif sort == "rating":
        query = query.order_by(desc(MarketplaceItem.avg_rating))
    else:
        query = query.order_by(desc(MarketplaceItem.created_at))

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": item.id,
                "publisher_id": item.publisher_id,
                "resource_type": item.resource_type,
                "title": item.title,
                "description": item.description,
                "category": item.category,
                "tags": item.tags,
                "download_count": item.download_count,
                "avg_rating": item.avg_rating,
                "rating_count": item.rating_count,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/categories")
async def list_categories():
    """List available marketplace categories."""
    return {
        "categories": [
            {"value": c.value, "label": c.value.title()}
            for c in MarketplaceCategory
        ]
    }


@router.get("/{item_id}")
async def get_marketplace_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed marketplace item."""
    item = await db.get(MarketplaceItem, item_id)
    if not item or not item.is_published:
        raise HTTPException(404, "Item not found")
    return {
        "id": item.id,
        "publisher_id": item.publisher_id,
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
        "title": item.title,
        "description": item.description,
        "category": item.category,
        "tags": item.tags,
        "download_count": item.download_count,
        "avg_rating": item.avg_rating,
        "rating_count": item.rating_count,
        "preview_data": item.preview_data,
        "created_at": item.created_at.isoformat(),
    }


@router.post("")
async def publish_to_marketplace(
    payload: MarketplacePublish,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a resource to the marketplace."""
    # Verify ownership
    if payload.resource_type == "workflow":
        from app.models.workflow import Workflow
        resource = await db.get(Workflow, payload.resource_id)
        if not resource or resource.user_id != str(current_user.id):
            raise HTTPException(403, "Not the owner of this resource")
        preview = {"node_count": len(resource.graph_json.get("nodes", [])), "tags": resource.tags}
    elif payload.resource_type == "library_item":
        from app.models.library import LibraryItem
        resource = await db.get(LibraryItem, payload.resource_id)
        if not resource or resource.user_id != str(current_user.id):
            raise HTTPException(403, "Not the owner of this resource")
        preview = {"type": resource.type.value if hasattr(resource.type, 'value') else str(resource.type), "tags": resource.tags}
    else:
        raise HTTPException(400, f"Unsupported resource_type: {payload.resource_type}")

    # Check duplicate
    existing = await db.execute(
        select(MarketplaceItem).where(
            MarketplaceItem.resource_type == payload.resource_type,
            MarketplaceItem.resource_id == payload.resource_id,
        )
    )
    if existing.scalar():
        raise HTTPException(409, "Resource already published")

    item = MarketplaceItem(
        id=str(uuid.uuid4()),
        publisher_id=str(current_user.id),
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        tags=payload.tags,
        preview_data=preview,
    )
    db.add(item)
    await db.commit()
    return {"id": item.id, "status": "published"}


@router.delete("/{item_id}")
async def unpublish_from_marketplace(
    item_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove item from marketplace."""
    item = await db.get(MarketplaceItem, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item.publisher_id != str(current_user.id):
        raise HTTPException(403, "Not the publisher")
    await db.delete(item)
    await db.commit()
    return {"status": "ok"}


@router.post("/{item_id}/install")
async def install_marketplace_item(
    item_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Install (clone) a marketplace item to user's account."""
    item = await db.get(MarketplaceItem, item_id)
    if not item or not item.is_published:
        raise HTTPException(404, "Item not found")

    cloned_id = str(uuid.uuid4())

    if item.resource_type == "workflow":
        from app.models.workflow import Workflow
        original = await db.get(Workflow, item.resource_id)
        if not original:
            raise HTTPException(404, "Original workflow not found")
        clone = Workflow(
            id=cloned_id,
            user_id=str(current_user.id),
            name=f"{original.name} (Marketplace)",
            description=original.description,
            graph_json=original.graph_json,
            tags=original.tags,
        )
        db.add(clone)

    elif item.resource_type == "library_item":
        from app.models.library import LibraryItem
        original = await db.get(LibraryItem, item.resource_id)
        if not original:
            raise HTTPException(404, "Original item not found")
        clone = LibraryItem(
            id=cloned_id,
            user_id=str(current_user.id),
            name=f"{original.name} (Marketplace)",
            type=original.type,
            description=original.description,
            resource_id=str(uuid.uuid4()),
            tags=original.tags,
        )
        db.add(clone)
    else:
        raise HTTPException(400, f"Cannot install resource_type: {item.resource_type}")

    # Increment download count
    item.download_count += 1
    await db.commit()

    return {"id": cloned_id, "status": "installed"}


@router.post("/{item_id}/review")
async def review_marketplace_item(
    item_id: str,
    payload: MarketplaceReviewCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add or update a review."""
    item = await db.get(MarketplaceItem, item_id)
    if not item or not item.is_published:
        raise HTTPException(404, "Item not found")

    # Check existing review
    existing = await db.execute(
        select(MarketplaceReview).where(
            MarketplaceReview.item_id == item_id,
            MarketplaceReview.user_id == str(current_user.id),
        )
    )
    review = existing.scalar()
    if review:
        review.rating = payload.rating
        review.comment = payload.comment
    else:
        review = MarketplaceReview(
            id=str(uuid.uuid4()),
            item_id=item_id,
            user_id=str(current_user.id),
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(review)

    await db.flush()

    # Recalculate avg rating
    avg_result = await db.execute(
        select(
            func.avg(MarketplaceReview.rating),
            func.count(MarketplaceReview.id),
        ).where(MarketplaceReview.item_id == item_id)
    )
    row = avg_result.one()
    item.avg_rating = float(row[0] or 0)
    item.rating_count = int(row[1] or 0)

    await db.commit()
    return {"status": "ok", "avg_rating": item.avg_rating, "rating_count": item.rating_count}


@router.get("/{item_id}/reviews")
async def list_reviews(
    item_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """List reviews for a marketplace item."""
    offset = (page - 1) * per_page
    result = await db.execute(
        select(MarketplaceReview)
        .where(MarketplaceReview.item_id == item_id)
        .order_by(desc(MarketplaceReview.created_at))
        .offset(offset)
        .limit(per_page)
    )
    reviews = result.scalars().all()
    return {
        "reviews": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat(),
            }
            for r in reviews
        ]
    }
