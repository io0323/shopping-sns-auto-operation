from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.harness.cost_guard import BudgetExceededError, check_budget, get_month_to_date_cost_jpy
from app.models import Base, Job, LlmUsage


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_usage(session: Session, cost_jpy: float, created_at: datetime) -> None:
    job = Job(pipeline="daily", step="generate", status="running")
    session.add(job)
    session.flush()
    usage = LlmUsage(
        job_id=job.id,
        agent="generator",
        model="claude-sonnet-5",
        input_tokens=100,
        output_tokens=100,
        estimated_cost_jpy=cost_jpy,
        created_at=created_at,
    )
    session.add(usage)
    session.flush()


def test_get_month_to_date_cost_sums_only_current_month() -> None:
    session = _make_session()
    _add_usage(session, 500.0, datetime(2026, 7, 1))
    _add_usage(session, 300.0, datetime(2026, 7, 20))
    _add_usage(session, 999.0, datetime(2026, 6, 30))
    session.commit()

    total = get_month_to_date_cost_jpy(session, as_of=date(2026, 7, 21))
    assert total == pytest.approx(800.0)


def test_check_budget_raises_when_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    _add_usage(session, 5000.0, datetime(2026, 7, 1))
    session.commit()

    fake_settings = MagicMock(monthly_llm_budget_jpy=3000)
    monkeypatch.setattr("app.harness.cost_guard.get_settings", lambda: fake_settings)

    with pytest.raises(BudgetExceededError):
        check_budget(session, as_of=date(2026, 7, 21))


def test_check_budget_passes_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    _add_usage(session, 100.0, datetime(2026, 7, 1))
    session.commit()

    fake_settings = MagicMock(monthly_llm_budget_jpy=3000)
    monkeypatch.setattr("app.harness.cost_guard.get_settings", lambda: fake_settings)

    check_budget(session, as_of=date(2026, 7, 21))
