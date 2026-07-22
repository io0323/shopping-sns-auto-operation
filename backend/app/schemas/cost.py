from pydantic import BaseModel


class AgentCost(BaseModel):
    agent: str
    input_tokens: int
    output_tokens: int
    cost_jpy: float


class CostSummary(BaseModel):
    month: str
    total_cost_jpy: float
    budget_jpy: int
    by_agent: list[AgentCost]
