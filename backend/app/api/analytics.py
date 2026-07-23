import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Job, Product, PromptVersion, Result
from app.schemas.analytics import AnalyticsSummary, GenreKpi
from app.schemas.learning import LearningReportOut
from app.schemas.prompt import PromptVersionOut

router = APIRouter()


@router.get("/analytics/summary")
def get_analytics_summary(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    session: Session = Depends(get_db),
) -> AnalyticsSummary:
    stmt = select(Result, Product).join(Product, Result.product_id == Product.id)
    if date_from is not None:
        stmt = stmt.where(Result.report_date_from >= date_from)
    if date_to is not None:
        stmt = stmt.where(Result.report_date_to <= date_to)
    rows = session.execute(stmt).all()

    genre_totals: dict[str, GenreKpi] = {}
    for result, product in rows:
        kpi = genre_totals.setdefault(
            product.genre_id,
            GenreKpi(
                genre_id=product.genre_id,
                genre_name=product.genre_name,
                clicks=0,
                conversions=0,
                revenue=0,
            ),
        )
        kpi.clicks += result.clicks
        kpi.conversions += result.conversions
        kpi.revenue += result.revenue

    return AnalyticsSummary(
        date_from=date_from,
        date_to=date_to,
        clicks=sum(kpi.clicks for kpi in genre_totals.values()),
        conversions=sum(kpi.conversions for kpi in genre_totals.values()),
        revenue=sum(kpi.revenue for kpi in genre_totals.values()),
        by_genre=sorted(genre_totals.values(), key=lambda kpi: kpi.revenue, reverse=True),
    )


@router.get("/analytics/learning-report")
def get_learning_report(session: Session = Depends(get_db)) -> LearningReportOut:
    stmt = (
        select(Job)
        .where(Job.pipeline == "weekly", Job.step == "learning", Job.status == "done")
        .order_by(Job.finished_at.desc())
        .limit(1)
    )
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return LearningReportOut(
            run_date=None,
            status="no_report",
            data_point_count=None,
            report=None,
            proposed_prompt_version=None,
        )

    payload = job.payload or {}
    result = payload.get("result", {})

    proposed_prompt_version = None
    proposed_id = result.get("proposed_prompt_version_id")
    if proposed_id:
        prompt_version = session.get(PromptVersion, uuid.UUID(proposed_id))
        if prompt_version is not None:
            proposed_prompt_version = PromptVersionOut.model_validate(prompt_version)

    return LearningReportOut(
        run_date=payload.get("run_date"),
        status=result.get("status", "no_report"),
        data_point_count=result.get("data_point_count"),
        report=result.get("report"),
        proposed_prompt_version=proposed_prompt_version,
    )
