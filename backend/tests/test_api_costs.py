from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import make_job, make_llm_usage


def test_get_costs_aggregates_by_agent_for_month(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    job = make_job(session)
    make_llm_usage(
        session,
        job,
        agent="generator",
        input_tokens=100,
        output_tokens=200,
        estimated_cost_jpy=10.0,
        created_at=datetime(2026, 7, 5),
    )
    make_llm_usage(
        session,
        job,
        agent="evaluator",
        input_tokens=50,
        output_tokens=50,
        estimated_cost_jpy=5.0,
        created_at=datetime(2026, 7, 10),
    )
    make_llm_usage(
        session,
        job,
        agent="generator",
        input_tokens=10,
        output_tokens=10,
        estimated_cost_jpy=999.0,
        created_at=datetime(2026, 6, 1),
    )
    session.close()

    response = api_client.get("/api/v1/costs", params={"month": "2026-07"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_cost_jpy"] == 15.0
    by_agent = {row["agent"]: row for row in body["by_agent"]}
    assert by_agent["generator"]["cost_jpy"] == 10.0
    assert by_agent["evaluator"]["cost_jpy"] == 5.0


def test_get_costs_rejects_invalid_month_format(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/costs", params={"month": "2026-7"})
    assert response.status_code == 422
