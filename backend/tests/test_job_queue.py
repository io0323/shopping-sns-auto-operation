from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.harness.job_queue import finish_step, get_step_job, is_pipeline_running, start_step
from app.models import Base


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_is_pipeline_running_false_when_no_jobs() -> None:
    session = _make_session()
    assert is_pipeline_running(session, "daily") is False


def test_is_pipeline_running_true_while_step_running() -> None:
    session = _make_session()
    start_step(session, "daily", "research", date(2026, 7, 21))
    assert is_pipeline_running(session, "daily") is True


def test_is_pipeline_running_false_after_all_steps_finish() -> None:
    session = _make_session()
    job = start_step(session, "daily", "research", date(2026, 7, 21))
    finish_step(session, job, status="done", result={"genres": 1})
    assert is_pipeline_running(session, "daily") is False


def test_get_step_job_returns_matching_run_date_only() -> None:
    session = _make_session()
    job_today = start_step(session, "daily", "research", date(2026, 7, 21))
    finish_step(session, job_today, status="done", result={"genres": 1})
    job_yesterday = start_step(session, "daily", "research", date(2026, 7, 20))
    finish_step(session, job_yesterday, status="done", result={"genres": 2})

    found = get_step_job(session, "daily", "research", date(2026, 7, 21))
    assert found is not None
    assert found.id == job_today.id
    assert (found.payload or {}).get("result") == {"genres": 1}


def test_get_step_job_returns_none_when_no_match() -> None:
    session = _make_session()
    assert get_step_job(session, "daily", "research", date(2026, 7, 21)) is None


def test_finish_step_records_error_on_failure() -> None:
    session = _make_session()
    job = start_step(session, "daily", "generate", date(2026, 7, 21))
    finish_step(session, job, status="failed", error="boom")
    assert job.status == "failed"
    assert job.error == "boom"
    assert job.finished_at is not None
