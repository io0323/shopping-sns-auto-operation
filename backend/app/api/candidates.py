import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.generator import build_generator_prompt
from app.agents.manual_content import (
    ManualContentParseError,
    import_manual_content,
    parse_manual_content,
)
from app.core.db import get_db
from app.models import Candidate, Product
from app.schemas.candidate import (
    CandidateListResponse,
    CandidateOut,
    CandidatePromptOut,
    ManualContentOut,
    ManualContentRequest,
)
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


def _load_candidate_with_product(
    session: Session, candidate_id: uuid.UUID
) -> tuple[Candidate, Product]:
    row = session.execute(
        select(Candidate, Product)
        .join(Product, Candidate.product_id == Product.id)
        .where(Candidate.id == candidate_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="候補が見つかりません")
    candidate, product = row
    return candidate, product


@router.get("/candidates/{candidate_id}/prompt")
def get_candidate_prompt(
    candidate_id: uuid.UUID,
    session: Session = Depends(get_db),
) -> CandidatePromptOut:
    """Generator AgentがLLMへ送るのと同一のプロンプトを書き出す。

    チャットUI(claude.ai等)へ貼り付けて手動生成し、結果を
    `POST /candidates/{id}/manual-content` で取り込むための経路。
    """
    candidate, product = _load_candidate_with_product(session, candidate_id)
    prompt, prompt_version = build_generator_prompt(session, product)
    return CandidatePromptOut(
        candidate_id=candidate.id,
        product_id=product.id,
        product_name=product.name,
        prompt_version=prompt_version,
        prompt=prompt,
    )


@router.post("/candidates/{candidate_id}/manual-content")
def create_manual_content(
    candidate_id: uuid.UUID,
    payload: ManualContentRequest,
    session: Session = Depends(get_db),
) -> ManualContentOut:
    """手動生成したJSONを取り込む。LLM評価は行わないため常に`needs_review`。"""
    candidate, product = _load_candidate_with_product(session, candidate_id)

    try:
        generated = parse_manual_content(payload.content)
    except ManualContentParseError as exc:
        raise HTTPException(status_code=422, detail="; ".join(exc.field_errors)) from exc

    # 書き出し時のprompt_versionを優先し、未指定なら現在の有効版を記録する。
    prompt_version = payload.prompt_version
    if prompt_version is None:
        _, prompt_version = build_generator_prompt(session, product)

    content, violations = import_manual_content(
        session, candidate, product, generated, prompt_version
    )
    return ManualContentOut(
        content_id=content.id,
        candidate_id=candidate.id,
        status=content.status,
        generation_source=content.generation_source,
        prompt_version=content.prompt_version,
        rule_violations=violations,
    )
