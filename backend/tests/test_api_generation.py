import json
from datetime import date
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import PromptVersion
from tests.conftest import make_candidate, make_product


def _content_json() -> str:
    return json.dumps(
        {
            "title": "おすすめ商品",
            "description": "あ" * 100,
            "hashtags": ["#a", "#b", "#c", "#d", "#e"],
            "x_post": "投稿テキスト #ad",
            "cta": "今すぐチェック",
        },
        ensure_ascii=False,
    )


def _eval_json_pass() -> str:
    return json.dumps(
        {
            "total": 90,
            "scores": {
                "natural": 18,
                "readability": 18,
                "appeal": 18,
                "uniqueness": 18,
                "compliance": 18,
            },
            "verdict": "pass",
            "improvement": None,
        },
        ensure_ascii=False,
    )


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self._responses = iter(
            [
                _content_json(),
                _eval_json_pass(),
            ]
        )
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        text = next(self._responses)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=10),
        )


def test_generate_returns_202_and_job_id_then_pollable(
    api_client: TestClient, db_session_factory: sessionmaker[Session], monkeypatch
) -> None:
    session = db_session_factory()
    product = make_product(session)
    candidate = make_candidate(session, product, selected_date=date(2026, 7, 22))
    candidate_id = candidate.id
    session.add_all(
        [
            PromptVersion(
                agent="generator", version="gen-v1", body="{product_json}", is_active=True
            ),
            PromptVersion(
                agent="evaluator",
                version="eval-v1",
                body="{content_json} {recent_posts}",
                is_active=True,
            ),
        ]
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "app.clients.llm.Anthropic", lambda api_key: _FakeAnthropicClient()
    )

    response = api_client.post(
        "/api/v1/generate", json={"candidate_ids": [str(candidate_id)]}
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job_response = api_client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["status"] == "done"
    assert job_body["payload"]["result"]["generated"] == 1

    contents_response = api_client.get(
        "/api/v1/contents", params={"status": "evaluated"}
    )
    assert contents_response.json()["meta"]["total"] == 1


def test_generate_rejects_unknown_candidate_ids(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/generate",
        json={"candidate_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 422


def test_generate_rejects_empty_candidate_ids(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/generate", json={"candidate_ids": []})
    assert response.status_code == 422


def test_get_job_404_when_missing(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
