from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Candidate, Product
from app.schemas.candidate import CandidateListResponse, CandidateOut
from app.schemas.common import PageMeta

router = APIRouter()


@router.get("/candidates")
def list_candidates(
    date_: date = Query(..., alias="date"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> CandidateListResponse:
    stmt = (
        select(Candidate, Product)
        .join(Product, Candidate.product_id == Product.id)
        .where(Candidate.selected_date == date_)
    )

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = (
        stmt.order_by(Candidate.score.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    rows = session.execute(stmt).all()

    items = [
        CandidateOut(
            id=candidate.id,
            product_id=product.id,
            product_name=product.name,
            genre_name=product.genre_name,
            shop_name=product.shop_name,
            item_url=product.item_url,
            image_url=product.image_url,
            selected_date=candidate.selected_date,
            score=candidate.score,
            score_breakdown=candidate.score_breakdown,
            status=candidate.status,
        )
        for candidate, product in rows
    ]

    return CandidateListResponse(
        items=items, meta=PageMeta(page=page, per_page=per_page, total=total)
    )
