import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.evaluator import run_generate_and_evaluate
from app.agents.research import StrategyConfig, run_daily_research
from app.agents.selection import ScoringWeights, SeasonalityConfig, run_daily_selection
from app.clients.llm import LlmClient
from app.clients.rakuten_api import RakutenApiClient
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.harness.cost_guard import BudgetExceededError, check_budget
from app.harness.job_queue import (
    PipelineAlreadyRunningError,
    finish_step,
    get_step_job,
    is_pipeline_running,
    start_step,
)
from app.models import Candidate, Content, Job, Product

logger = logging.getLogger(__name__)

PIPELINE_NAME = "daily"


def _run_step(
    session: Session,
    pipeline: str,
    step: str,
    run_date: date,
    action: Callable[[Job], dict[str, Any]],
) -> dict[str, Any]:
    existing = get_step_job(session, pipeline, step, run_date)
    if existing is not None and existing.status == "done":
        logger.info("pipeline step already done, skipping: step=%s run_date=%s", step, run_date)
        return dict((existing.payload or {}).get("result", {}))

    job = start_step(session, pipeline, step, run_date)
    try:
        result = action(job)
    except Exception as exc:
        logger.exception("pipeline step failed: step=%s", step)
        finish_step(session, job, status="failed", error=str(exc))
        raise
    finish_step(session, job, status="done", result=result)
    return result


def _generate_and_evaluate_candidates(
    session: Session, llm_client: LlmClient, run_date: date, job: Job
) -> dict[str, Any]:
    stmt = select(Candidate).where(
        Candidate.selected_date == run_date, Candidate.status == "selected"
    )
    candidates = list(session.execute(stmt).scalars().all())

    generated = 0
    needs_review = 0
    failed = 0
    budget_exceeded = False

    for candidate in candidates:
        try:
            check_budget(session)
        except BudgetExceededError:
            budget_exceeded = True
            logger.warning("月間LLM予算を超過したため以降の生成を停止します")
            break

        product = session.get(Product, candidate.product_id)
        if product is None:
            failed += 1
            continue

        try:
            content = run_generate_and_evaluate(session, llm_client, job.id, product, candidate)
        except Exception:
            logger.exception("candidate generation failed: candidate_id=%s", candidate.id)
            failed += 1
            continue

        candidate.status = "generated"
        session.add(candidate)
        session.commit()

        if content.status == "evaluated":
            generated += 1
        else:
            needs_review += 1

    return {
        "candidates": len(candidates),
        "generated": generated,
        "needs_review": needs_review,
        "failed": failed,
        "budget_exceeded": budget_exceeded,
    }


def _summarize_saved_contents(session: Session, run_date: date) -> dict[str, Any]:
    stmt = (
        select(Content)
        .join(Candidate, Content.candidate_id == Candidate.id)
        .where(Candidate.selected_date == run_date)
    )
    contents = list(session.execute(stmt).scalars().all())
    evaluated = sum(1 for c in contents if c.status == "evaluated")
    needs_review = sum(1 for c in contents if c.status == "needs_review")
    return {"total": len(contents), "evaluated": evaluated, "needs_review": needs_review}


def _send_slack_notification(message: str) -> None:
    settings = get_settings()
    if not settings.slack_webhook_url:
        return
    try:
        httpx.post(settings.slack_webhook_url, json={"text": message}, timeout=5.0)
    except httpx.HTTPError:
        logger.exception("Slack通知の送信に失敗しました")


def run_daily_pipeline(
    session: Session,
    run_date: date | None = None,
    rakuten_client: RakutenApiClient | None = None,
    llm_client: LlmClient | None = None,
    strategy: StrategyConfig | None = None,
    weights: ScoringWeights | None = None,
    seasonality: SeasonalityConfig | None = None,
) -> dict[str, Any]:
    if is_pipeline_running(session, PIPELINE_NAME):
        raise PipelineAlreadyRunningError(
            f"パイプライン({PIPELINE_NAME})は既に実行中です"
        )

    run_date = run_date or date.today()
    rakuten_client = rakuten_client or RakutenApiClient()
    llm_client = llm_client or LlmClient(session)

    research_result = _run_step(
        session,
        PIPELINE_NAME,
        "research",
        run_date,
        lambda _job: run_daily_research(
            session, rakuten_client, strategy=strategy, run_date=run_date
        ),
    )

    selection_result = _run_step(
        session,
        PIPELINE_NAME,
        "selection",
        run_date,
        lambda _job: {
            "candidates": len(
                run_daily_selection(
                    session,
                    run_date=run_date,
                    strategy=strategy,
                    weights=weights,
                    seasonality=seasonality,
                )
            )
        },
    )

    generate_result = _run_step(
        session,
        PIPELINE_NAME,
        "generate",
        run_date,
        lambda job: _generate_and_evaluate_candidates(session, llm_client, run_date, job),
    )

    save_result = _run_step(
        session,
        PIPELINE_NAME,
        "save",
        run_date,
        lambda _job: _summarize_saved_contents(session, run_date),
    )

    message = f"本日の候補{save_result['evaluated']}件(要確認{save_result['needs_review']}件)"
    if generate_result.get("budget_exceeded"):
        message += " ※月間LLM予算上限に達したため生成を一部スキップしました"

    def _notify(_job: Job) -> dict[str, Any]:
        logger.info(message)
        _send_slack_notification(message)
        return {"message": message}

    notify_result = _run_step(session, PIPELINE_NAME, "notify", run_date, _notify)

    return {
        "run_date": run_date.isoformat(),
        "research": research_result,
        "selection": selection_result,
        "generate": generate_result,
        "save": save_result,
        "notify": notify_result,
    }


def _run_daily_pipeline_job() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            run_daily_pipeline(session)
        except PipelineAlreadyRunningError:
            logger.warning("scheduled daily pipeline skipped: already running")
        except Exception:
            logger.exception("scheduled daily pipeline failed")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_daily_pipeline_job,
        CronTrigger(hour=5, minute=0),
        id=f"{PIPELINE_NAME}-pipeline",
        replace_existing=True,
    )
    return scheduler


__all__ = [
    "PipelineAlreadyRunningError",
    "create_scheduler",
    "run_daily_pipeline",
]
