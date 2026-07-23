import json
import logging
import re
import uuid
from datetime import datetime
from statistics import mean
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.generator import load_active_prompt, strip_code_fence
from app.clients.llm import LlmClient
from app.core.config import get_settings
from app.harness.cost_guard import BudgetExceededError, check_budget
from app.models import Candidate, Content, Product, PromptVersion, Result

logger = logging.getLogger(__name__)

MIN_DATASET_SIZE = 30
_GENERATOR_VERSION_RE = re.compile(r"^gen-v(\d+)$")


class LearningDataPoint(BaseModel):
    content_id: uuid.UUID
    product_id: uuid.UUID
    genre_name: str
    description_length: int
    hashtag_count: int
    quality_natural: int | None
    quality_readability: int | None
    quality_appeal: int | None
    quality_uniqueness: int | None
    quality_compliance: int | None
    edited_by_human: bool
    candidate_score: float | None
    clicks: int
    conversions: int
    revenue: int


class LearningReportContent(BaseModel):
    summary: str
    high_performer_patterns: list[str]
    low_performer_patterns: list[str]
    recommendations: list[str]


class LearningResult(BaseModel):
    report: LearningReportContent
    proposed_generator_prompt: str
    rationale: str


def _match_content(session: Session, result: Result) -> Content | None:
    period_start = datetime.combine(result.report_date_from, datetime.min.time())
    period_end = datetime.combine(result.report_date_to, datetime.max.time())
    stmt = (
        select(Content)
        .where(
            Content.product_id == result.product_id,
            Content.status == "posted",
            Content.posted_at.is_not(None),
            Content.posted_at >= period_start,
            Content.posted_at <= period_end,
        )
        .order_by(Content.posted_at.desc())
    )
    return session.execute(stmt).scalars().first()


def build_learning_dataset(session: Session) -> list[LearningDataPoint]:
    results = session.execute(select(Result)).scalars().all()
    data_points: list[LearningDataPoint] = []

    for result in results:
        content = _match_content(session, result)
        if content is None:
            continue
        product = session.get(Product, result.product_id)
        if product is None:
            continue
        candidate = session.get(Candidate, content.candidate_id)
        breakdown = content.quality_breakdown or {}

        data_points.append(
            LearningDataPoint(
                content_id=content.id,
                product_id=product.id,
                genre_name=product.genre_name,
                description_length=len(content.description),
                hashtag_count=len(content.hashtags),
                quality_natural=breakdown.get("natural"),
                quality_readability=breakdown.get("readability"),
                quality_appeal=breakdown.get("appeal"),
                quality_uniqueness=breakdown.get("uniqueness"),
                quality_compliance=breakdown.get("compliance"),
                edited_by_human=content.edited_by_human,
                candidate_score=candidate.score if candidate is not None else None,
                clicks=result.clicks,
                conversions=result.conversions,
                revenue=result.revenue,
            )
        )

    return data_points


def split_high_low_performers(
    dataset: list[LearningDataPoint],
) -> tuple[list[LearningDataPoint], list[LearningDataPoint]]:
    ordered = sorted(dataset, key=lambda d: d.revenue, reverse=True)
    group_size = max(1, len(ordered) // 3)
    return ordered[:group_size], ordered[-group_size:]


def _avg(values: list[float | None]) -> float | None:
    filtered = [v for v in values if v is not None]
    return round(mean(filtered), 2) if filtered else None


def summarize_group(group: list[LearningDataPoint]) -> dict[str, Any]:
    genre_counts: dict[str, int] = {}
    for point in group:
        genre_counts[point.genre_name] = genre_counts.get(point.genre_name, 0) + 1

    return {
        "count": len(group),
        "avg_revenue": _avg([p.revenue for p in group]),
        "avg_clicks": _avg([p.clicks for p in group]),
        "avg_conversions": _avg([p.conversions for p in group]),
        "avg_description_length": _avg([p.description_length for p in group]),
        "avg_hashtag_count": _avg([p.hashtag_count for p in group]),
        "avg_quality_natural": _avg([p.quality_natural for p in group]),
        "avg_quality_readability": _avg([p.quality_readability for p in group]),
        "avg_quality_appeal": _avg([p.quality_appeal for p in group]),
        "avg_quality_uniqueness": _avg([p.quality_uniqueness for p in group]),
        "avg_quality_compliance": _avg([p.quality_compliance for p in group]),
        "avg_candidate_score": _avg([p.candidate_score for p in group]),
        "edited_by_human_ratio": round(
            sum(1 for p in group if p.edited_by_human) / len(group), 2
        )
        if group
        else None,
        "genre_distribution": genre_counts,
    }


def render_learning_prompt(
    template: str,
    current_generator_prompt: str,
    data_point_count: int,
    high_summary: dict[str, Any],
    low_summary: dict[str, Any],
) -> str:
    prompt = template.replace("{data_point_count}", str(data_point_count))
    prompt = prompt.replace("{high_group_json}", json.dumps(high_summary, ensure_ascii=False))
    prompt = prompt.replace("{low_group_json}", json.dumps(low_summary, ensure_ascii=False))
    prompt = prompt.replace("{current_generator_prompt}", current_generator_prompt)
    return prompt


def parse_learning_result(text: str) -> LearningResult:
    raw = strip_code_fence(text)
    data = json.loads(raw)
    return LearningResult.model_validate(data)


def _next_generator_version(session: Session) -> str:
    stmt = select(PromptVersion.version).where(PromptVersion.agent == "generator")
    max_n = 0
    for version in session.execute(stmt).scalars():
        match = _GENERATOR_VERSION_RE.match(version)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"gen-v{max_n + 1}"


def run_learning(session: Session, llm_client: LlmClient, job_id: uuid.UUID) -> dict[str, Any]:
    dataset = build_learning_dataset(session)
    if len(dataset) < MIN_DATASET_SIZE:
        return {
            "status": "insufficient_data",
            "data_point_count": len(dataset),
            "report": None,
            "proposed_prompt_version_id": None,
            "proposed_prompt_version": None,
        }

    try:
        check_budget(session)
    except BudgetExceededError:
        return {
            "status": "budget_exceeded",
            "data_point_count": len(dataset),
            "report": None,
            "proposed_prompt_version_id": None,
            "proposed_prompt_version": None,
        }

    high, low = split_high_low_performers(dataset)
    high_summary = summarize_group(high)
    low_summary = summarize_group(low)

    learning_prompt_version = load_active_prompt(session, "learning")
    generator_prompt_version = load_active_prompt(session, "generator")
    prompt = render_learning_prompt(
        learning_prompt_version.body,
        generator_prompt_version.body,
        len(dataset),
        high_summary,
        low_summary,
    )

    settings = get_settings()
    result = llm_client.complete(
        job_id=job_id,
        agent="learning",
        model=settings.model_learning,
        prompt=prompt,
        max_tokens=2048,
    )
    try:
        parsed = parse_learning_result(result.text)
    except (json.JSONDecodeError, ValidationError):
        logger.exception("learning agent response could not be parsed")
        return {
            "status": "invalid_llm_response",
            "data_point_count": len(dataset),
            "report": None,
            "proposed_prompt_version_id": None,
            "proposed_prompt_version": None,
        }

    next_version = _next_generator_version(session)
    proposed = PromptVersion(
        agent="generator",
        version=next_version,
        body=parsed.proposed_generator_prompt,
        is_active=False,
        note=parsed.rationale,
    )
    session.add(proposed)
    session.commit()

    return {
        "status": "completed",
        "data_point_count": len(dataset),
        "report": parsed.report.model_dump(),
        "proposed_prompt_version_id": str(proposed.id),
        "proposed_prompt_version": next_version,
    }
