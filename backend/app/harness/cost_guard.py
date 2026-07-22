from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import LlmUsage


class BudgetExceededError(Exception):
    pass


def get_month_to_date_cost_jpy(session: Session, as_of: date | None = None) -> float:
    as_of = as_of or date.today()
    month_start = datetime.combine(as_of.replace(day=1), datetime.min.time())
    stmt = select(func.coalesce(func.sum(LlmUsage.estimated_cost_jpy), 0.0)).where(
        LlmUsage.created_at >= month_start
    )
    return float(session.execute(stmt).scalar_one())


def get_cost_for_month(session: Session, year: int, month: int) -> float:
    month_start = datetime(year, month, 1)
    month_end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    stmt = select(func.coalesce(func.sum(LlmUsage.estimated_cost_jpy), 0.0)).where(
        LlmUsage.created_at >= month_start, LlmUsage.created_at < month_end
    )
    return float(session.execute(stmt).scalar_one())


def check_budget(session: Session, as_of: date | None = None) -> None:
    settings = get_settings()
    spent = get_month_to_date_cost_jpy(session, as_of)
    if spent >= settings.monthly_llm_budget_jpy:
        raise BudgetExceededError(
            f"月間LLM予算({settings.monthly_llm_budget_jpy}円)を超過しました: "
            f"現在{spent:.1f}円"
        )
