from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import OperationLog, PromptVersion
from tests.conftest import make_prompt_version


def test_activate_prompt_switches_active_version_and_logs(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    active = make_prompt_version(session, agent="generator", version="gen-v1", is_active=True)
    proposed = make_prompt_version(
        session, agent="generator", version="gen-v2", is_active=False, note="改善案"
    )
    session.close()

    response = api_client.post(
        "/api/v1/prompts/generator/activate", json={"prompt_version_id": str(proposed.id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is True
    assert body["version"] == "gen-v2"

    verify_session = db_session_factory()
    refreshed_active = verify_session.get(PromptVersion, active.id)
    refreshed_proposed = verify_session.get(PromptVersion, proposed.id)
    assert refreshed_active is not None and refreshed_active.is_active is False
    assert refreshed_proposed is not None and refreshed_proposed.is_active is True

    logs = verify_session.execute(select(OperationLog)).scalars().all()
    assert len(logs) == 1
    assert logs[0].operation == "activate_prompt"
    assert logs[0].target_id == proposed.id
    verify_session.close()


def test_activate_prompt_404_when_missing(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/prompts/generator/activate",
        json={"prompt_version_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_activate_prompt_404_when_agent_mismatch(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    evaluator_version = make_prompt_version(session, agent="evaluator", version="eval-v1")
    session.close()

    response = api_client.post(
        "/api/v1/prompts/generator/activate",
        json={"prompt_version_id": str(evaluator_version.id)},
    )
    assert response.status_code == 404


def test_activate_prompt_rejects_unknown_fields(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    version = make_prompt_version(session)
    session.close()

    response = api_client.post(
        "/api/v1/prompts/generator/activate",
        json={"prompt_version_id": str(version.id), "force": True},
    )
    assert response.status_code == 422
