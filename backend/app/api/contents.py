import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.operation_log import record_operation
from app.models import Content, Product
from app.schemas.common import PageMeta
from app.schemas.content import ContentListResponse, ContentOut, ContentUpdate

router = APIRouter()

_SORTABLE_FIELDS = {
    "created_at": Content.created_at,
    "updated_at": Content.updated_at,
    "scheduled_at": Content.scheduled_at,
    "quality_score": Content.quality_score,
}
_EDITABLE_FIELDS = ("title", "description", "hashtags", "x_post", "cta")


def _resolve_sort(sort: str | None) -> ColumnElement[Any]:
    sort = sort or "-created_at"
    descending = sort.startswith("-")
    field_name = sort[1:] if descending else sort
    column = _SORTABLE_FIELDS.get(field_name)
    if column is None:
        raise HTTPException(status_code=422, detail=f"不正なsortです: {sort}")
    return column.desc() if descending else column.asc()


def _to_content_out(content: Content, product_name: str) -> ContentOut:
    return ContentOut(
        id=content.id,
        product_id=content.product_id,
        candidate_id=content.candidate_id,
        product_name=product_name,
        title=content.title,
        description=content.description,
        hashtags=content.hashtags,
        x_post=content.x_post,
        cta=content.cta,
        quality_score=content.quality_score,
        quality_breakdown=content.quality_breakdown,
        eval_comment=content.eval_comment,
        regen_count=content.regen_count,
        prompt_version=content.prompt_version,
        status=content.status,
        scheduled_at=content.scheduled_at,
        posted_at=content.posted_at,
        edited_by_human=content.edited_by_human,
        created_at=content.created_at,
        updated_at=content.updated_at,
    )


def _get_content_or_404(session: Session, content_id: uuid.UUID) -> Content:
    content = session.get(Content, content_id)
    if content is None:
        raise HTTPException(status_code=404, detail="コンテンツが見つかりません")
    return content


@router.get("/contents")
def list_contents(
    status: list[str] | None = Query(None),
    sort: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> ContentListResponse:
    stmt = select(Content, Product.name).join(Product, Content.product_id == Product.id)
    if status:
        stmt = stmt.where(Content.status.in_(status))

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(_resolve_sort(sort)).offset((page - 1) * per_page).limit(per_page)
    rows = session.execute(stmt).all()

    items = [_to_content_out(content, product_name) for content, product_name in rows]
    return ContentListResponse(
        items=items, meta=PageMeta(page=page, per_page=per_page, total=total)
    )


@router.patch("/contents/{content_id}")
def update_content(
    content_id: uuid.UUID, payload: ContentUpdate, session: Session = Depends(get_db)
) -> ContentOut:
    content = _get_content_or_404(session, content_id)

    updates = payload.model_dump(exclude_unset=True)
    edited_fields = [field for field in _EDITABLE_FIELDS if field in updates]
    for field, value in updates.items():
        setattr(content, field, value)
    if edited_fields:
        content.edited_by_human = True

    session.add(content)
    if updates:
        record_operation(
            session,
            operation="edit",
            target_type="content",
            target_id=content.id,
            detail={"fields": list(updates.keys())},
        )
    session.commit()

    product = session.get(Product, content.product_id)
    product_name = product.name if product is not None else ""
    return _to_content_out(content, product_name)


@router.post("/contents/{content_id}/approve")
def approve_content(content_id: uuid.UUID, session: Session = Depends(get_db)) -> ContentOut:
    content = _get_content_or_404(session, content_id)
    content.status = "approved"
    session.add(content)
    record_operation(session, operation="approve", target_type="content", target_id=content.id)
    session.commit()

    product = session.get(Product, content.product_id)
    return _to_content_out(content, product.name if product is not None else "")


@router.post("/contents/{content_id}/reject")
def reject_content(content_id: uuid.UUID, session: Session = Depends(get_db)) -> ContentOut:
    content = _get_content_or_404(session, content_id)
    content.status = "rejected"
    session.add(content)
    record_operation(session, operation="reject", target_type="content", target_id=content.id)
    session.commit()

    product = session.get(Product, content.product_id)
    return _to_content_out(content, product.name if product is not None else "")


@router.post("/contents/{content_id}/mark-posted")
def mark_content_posted(content_id: uuid.UUID, session: Session = Depends(get_db)) -> ContentOut:
    content = _get_content_or_404(session, content_id)
    content.status = "posted"
    content.posted_at = datetime.now(UTC)
    session.add(content)
    record_operation(
        session, operation="mark-posted", target_type="content", target_id=content.id
    )
    session.commit()

    product = session.get(Product, content.product_id)
    return _to_content_out(content, product.name if product is not None else "")
