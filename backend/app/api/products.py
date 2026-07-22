import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Candidate, Product, ProductMetric
from app.schemas.common import PageMeta
from app.schemas.product import ProductListResponse, ProductMetricOut, ProductOut

router = APIRouter()


@router.get("/products")
def list_products(
    genre_id: str | None = Query(None),
    min_score: float | None = Query(None),
    excluded: bool | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> ProductListResponse:
    stmt = select(Product)
    if genre_id is not None:
        stmt = stmt.where(Product.genre_id == genre_id)
    if excluded is not None:
        stmt = stmt.where(Product.excluded == excluded)
    if min_score is not None:
        qualifying = select(Candidate.product_id).where(Candidate.score >= min_score).distinct()
        stmt = stmt.where(Product.id.in_(qualifying))

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = (
        stmt.order_by(Product.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    products = session.execute(stmt).scalars().all()

    return ProductListResponse(
        items=[ProductOut.model_validate(p) for p in products],
        meta=PageMeta(page=page, per_page=per_page, total=total),
    )


@router.get("/products/{product_id}/metrics")
def get_product_metrics(
    product_id: uuid.UUID, session: Session = Depends(get_db)
) -> list[ProductMetricOut]:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    stmt = (
        select(ProductMetric)
        .where(ProductMetric.product_id == product_id)
        .order_by(ProductMetric.snapshot_date.asc())
    )
    metrics = session.execute(stmt).scalars().all()
    return [ProductMetricOut.model_validate(m) for m in metrics]
