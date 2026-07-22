from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import make_candidate, make_content, make_product


def test_get_export_queue_returns_only_approved(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    make_content(session, product, candidate, status="approved", x_post="投稿 #ad")
    make_content(session, product, candidate, status="needs_review")
    session.close()

    response = api_client.get("/api/v1/export/queue")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["has_ad_disclosure"] is True
    assert "room_text" in item
    assert isinstance(item["checklist"], list)


def test_get_export_queue_empty_when_none_approved(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/export/queue")
    assert response.status_code == 200
    assert response.json()["items"] == []
