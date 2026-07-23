from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.harness.job_queue import finish_step, start_step
from tests.conftest import make_product, make_prompt_version, make_result


def test_analytics_summary_aggregates_totals_and_by_genre(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product_a = make_product(
        session, item_code="shop1:0001", genre_id="100283", genre_name="スイーツ"
    )
    product_b = make_product(
        session, item_code="shop2:0002", genre_id="100001", genre_name="家電"
    )
    make_result(session, product_a, clicks=10, conversions=1, revenue=500)
    make_result(
        session,
        product_a,
        report_date_from=date(2026, 7, 8),
        report_date_to=date(2026, 7, 14),
        clicks=5,
        conversions=0,
        revenue=0,
    )
    make_result(session, product_b, clicks=3, conversions=2, revenue=2000)
    session.close()

    response = api_client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["clicks"] == 18
    assert body["conversions"] == 3
    assert body["revenue"] == 2500
    genres = {g["genre_id"]: g for g in body["by_genre"]}
    assert genres["100283"]["clicks"] == 15
    assert genres["100001"]["revenue"] == 2000


def test_analytics_summary_filters_by_date_range(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    make_result(
        session,
        product,
        report_date_from=date(2026, 6, 1),
        report_date_to=date(2026, 6, 7),
        clicks=100,
    )
    make_result(
        session,
        product,
        report_date_from=date(2026, 7, 1),
        report_date_to=date(2026, 7, 7),
        clicks=5,
    )
    session.close()

    response = api_client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert response.status_code == 200
    assert response.json()["clicks"] == 5


def test_learning_report_returns_no_report_when_never_run(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/analytics/learning-report")
    assert response.status_code == 200
    assert response.json()["status"] == "no_report"


def test_learning_report_returns_latest_completed_run(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    proposed = make_prompt_version(
        session, agent="generator", version="gen-v2", is_active=False, note="根拠"
    )

    job = start_step(session, "weekly", "learning", date(2026, 7, 19))
    finish_step(
        session,
        job,
        status="done",
        result={
            "status": "completed",
            "data_point_count": 30,
            "report": {
                "summary": "s",
                "high_performer_patterns": [],
                "low_performer_patterns": [],
                "recommendations": [],
            },
            "proposed_prompt_version_id": str(proposed.id),
            "proposed_prompt_version": "gen-v2",
        },
    )
    session.close()

    response = api_client.get("/api/v1/analytics/learning-report")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["data_point_count"] == 30
    assert body["proposed_prompt_version"]["version"] == "gen-v2"
    assert body["proposed_prompt_version"]["is_active"] is False
