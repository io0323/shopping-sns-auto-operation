from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.harness.cost_guard import get_cost_for_month
from app.models import LlmUsage
from app.schemas.cost import AgentCost, CostSummary

router = APIRouter()

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/costs")
def get_costs(
    month: str = Query(..., pattern=_MONTH_PATTERN),
    session: Session = Depends(get_db),
) -> CostSummary:
    year, month_num = (int(part) for part in month.split("-"))

    total = get_cost_for_month(session, year, month_num)

    month_start = datetime(year, month_num, 1)
    month_end = datetime(year + 1, 1, 1) if month_num == 12 else datetime(year, month_num + 1, 1)
    stmt = select(LlmUsage).where(
        LlmUsage.created_at >= month_start, LlmUsage.created_at < month_end
    )
    usages = session.execute(stmt).scalars().all()

    by_agent: dict[str, AgentCost] = {}
    for usage in usages:
        agent_cost = by_agent.setdefault(
            usage.agent,
            AgentCost(agent=usage.agent, input_tokens=0, output_tokens=0, cost_jpy=0.0),
        )
        agent_cost.input_tokens += usage.input_tokens
        agent_cost.output_tokens += usage.output_tokens
        agent_cost.cost_jpy += usage.estimated_cost_jpy

    settings = get_settings()
    return CostSummary(
        month=month,
        total_cost_jpy=total,
        budget_jpy=settings.monthly_llm_budget_jpy,
        by_agent=sorted(by_agent.values(), key=lambda a: a.cost_jpy, reverse=True),
    )
