from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import OperationLog
from tests.conftest import make_candidate, make_content, make_product


def test_list_contents_filters_by_status(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    make_content(session, product, candidate, status="evaluated")
    make_content(session, product, candidate, status="needs_review")
    make_content(session, product, candidate, status="approved")
    session.close()

    response = api_client.get(
        "/api/v1/contents", params=[("status", "evaluated"), ("status", "needs_review")]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    statuses = {item["status"] for item in body["items"]}
    assert statuses == {"evaluated", "needs_review"}


def test_list_contents_invalid_sort_returns_422(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/contents", params={"sort": "not_a_field"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_content_updates_fields_and_sets_edited_by_human(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate)
    content_id = content.id
    assert content.edited_by_human is False
    session.close()

    response = api_client.patch(
        f"/api/v1/contents/{content_id}", json={"title": "編集後タイトル"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "編集後タイトル"
    assert body["edited_by_human"] is True

    log_session = db_session_factory()
    logs = log_session.execute(select(OperationLog)).scalars().all()
    assert len(logs) == 1
    assert logs[0].operation == "edit"
    assert logs[0].target_type == "content"
    assert logs[0].target_id == content_id
    log_session.close()


def test_patch_content_schedule_only_does_not_set_edited_by_human(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate)
    content_id = content.id
    session.close()

    response = api_client.patch(
        f"/api/v1/contents/{content_id}",
        json={"scheduled_at": "2026-07-23T09:00:00Z"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["edited_by_human"] is False
    assert body["scheduled_at"] is not None


def test_patch_content_404_when_missing(api_client: TestClient) -> None:
    response = api_client.patch(
        "/api/v1/contents/00000000-0000-0000-0000-000000000000", json={"title": "x"}
    )
    assert response.status_code == 404


def test_patch_content_rejects_unknown_fields(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate)
    content_id = content.id
    session.close()

    response = api_client.patch(
        f"/api/v1/contents/{content_id}", json={"status": "approved"}
    )
    assert response.status_code == 422


def test_approve_content_updates_status_and_logs(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate, status="evaluated")
    content_id = content.id
    session.close()

    response = api_client.post(f"/api/v1/contents/{content_id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    log_session = db_session_factory()
    logs = log_session.execute(select(OperationLog)).scalars().all()
    assert len(logs) == 1
    assert logs[0].operation == "approve"
    log_session.close()


def test_reject_content_updates_status(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate, status="needs_review")
    content_id = content.id
    session.close()

    response = api_client.post(f"/api/v1/contents/{content_id}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_mark_posted_sets_status_and_posted_at(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product)
    content = make_content(session, product, candidate, status="approved")
    content_id = content.id
    session.close()

    response = api_client.post(f"/api/v1/contents/{content_id}/mark-posted")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "posted"
    assert body["posted_at"] is not None
