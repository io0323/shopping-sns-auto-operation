from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import make_candidate, make_product


def test_list_candidates_requires_date_param(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/candidates")
    assert response.status_code == 422


def test_list_candidates_returns_matching_date_sorted_by_score(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    p1 = make_product(session, item_code="shop1:0001", name="低スコア商品")
    p2 = make_product(session, item_code="shop1:0002", name="高スコア商品")
    make_candidate(session, p1, selected_date=date(2026, 7, 22), score=0.3)
    make_candidate(session, p2, selected_date=date(2026, 7, 22), score=0.9)
    make_candidate(session, p1, selected_date=date(2026, 7, 21), score=0.99)
    session.close()

    response = api_client.get("/api/v1/candidates", params={"date": "2026-07-22"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    assert body["items"][0]["product_name"] == "高スコア商品"
    assert body["items"][0]["score_breakdown"] == {"rank_trend": 0.5}
    assert body["items"][1]["product_name"] == "低スコア商品"


def test_list_candidates_empty_when_no_match(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/candidates", params={"date": "2026-01-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["meta"]["total"] == 0
