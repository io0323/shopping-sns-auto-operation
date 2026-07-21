from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job

RUNNING_STATUSES = ("pending", "running")


class PipelineAlreadyRunningError(Exception):
    pass


def is_pipeline_running(session: Session, pipeline: str) -> bool:
    stmt = (
        select(Job.id)
        .where(Job.pipeline == pipeline, Job.status.in_(RUNNING_STATUSES))
        .limit(1)
    )
    return session.execute(stmt).first() is not None


def get_step_job(session: Session, pipeline: str, step: str, run_date: date) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.pipeline == pipeline, Job.step == step)
        .order_by(Job.started_at.desc())
        .limit(20)
    )
    run_date_str = run_date.isoformat()
    for job in session.execute(stmt).scalars():
        payload = job.payload or {}
        if payload.get("run_date") == run_date_str:
            return job
    return None


def start_step(session: Session, pipeline: str, step: str, run_date: date) -> Job:
    job = Job(
        pipeline=pipeline,
        step=step,
        status="running",
        payload={"run_date": run_date.isoformat()},
        started_at=datetime.now(UTC),
    )
    session.add(job)
    session.commit()
    return job


def finish_step(
    session: Session,
    job: Job,
    *,
    status: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    job.status = status
    job.error = error
    job.finished_at = datetime.now(UTC)
    if result is not None:
        payload = dict(job.payload or {})
        payload["result"] = result
        job.payload = payload
    session.commit()
