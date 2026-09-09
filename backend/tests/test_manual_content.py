import json
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents.generator import build_generator_prompt, render_prompt
from app.agents.manual_content import (
    ManualContentParseError,
    parse_manual_content,
)
from app.models import Content
from tests.conftest import make_candidate, make_product, make_prompt_version

PROMPT_BODY = "以下の商品の投稿文をJSONで作成してください。\n\n{product_json}"

VALID_CONTENT = {
    "title": "朝の氷が夕方まで残る軽量ボトル",
    "description": (
        "500mlで約280gと軽く、通勤バッグに入れても肩に負担がかかりません。"
        "真空断熱の二重構造で冷たさが長く続き、結露しにくいので書類と一緒に持ち歩けます。"
        "口径が広く氷を入れやすいところも、日常使いでは効いてきます。"
    ),
    "hashtags": ["水筒", "ステンレスボトル", "通勤グッズ", "時短家事", "楽天room"],
    "x_post": "この軽さで真空断熱なのはうれしい。 #ad",
    "cta": "詳細は商品ページで確認",
}


def _valid_json() -> str:
    return json.dumps(VALID_CONTENT, ensure_ascii=False)


# --- プロンプト構築の共通化 -------------------------------------------------


def test_build_generator_prompt_matches_render_prompt(
    db_session_factory: sessionmaker[Session],
) -> None:
    """APIが書き出すプロンプトとGenerator Agentが送る本文が同一であること。"""
    session = db_session_factory()
    prompt_version = make_prompt_version(
        session, agent="generator", version="gen-v1", body=PROMPT_BODY
    )
    product = make_product(session)

    prompt, version = build_generator_prompt(session, product)

    assert version == prompt_version.version
    assert prompt == render_prompt(prompt_version.body, product, None)


def test_build_generator_prompt_appends_improvement_hint(
    db_session_factory: sessionmaker[Session],
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v1", body=PROMPT_BODY)
    product = make_product(session)

    prompt, _ = build_generator_prompt(session, product, "ハッシュタグを減らす")

    assert "ハッシュタグを減らす" in prompt


# --- JSONパース -------------------------------------------------------------


def test_parse_manual_content_accepts_plain_json() -> None:
    parsed = parse_manual_content(_valid_json())
    assert parsed.title == VALID_CONTENT["title"]


@pytest.mark.parametrize("fence", ["```json\n{body}\n```", "```\n{body}\n```"])
def test_parse_manual_content_strips_code_fence(fence: str) -> None:
    parsed = parse_manual_content(fence.format(body=_valid_json()))
    assert parsed.hashtags == VALID_CONTENT["hashtags"]


def test_parse_manual_content_rejects_invalid_json() -> None:
    with pytest.raises(ManualContentParseError) as exc:
        parse_manual_content("{title: これはJSONではない}")
    assert any("JSONとして解釈できません" in err for err in exc.value.field_errors)


def test_parse_manual_content_reports_missing_fields() -> None:
    payload = dict(VALID_CONTENT)
    del payload["x_post"]
    del payload["cta"]

    with pytest.raises(ManualContentParseError) as exc:
        parse_manual_content(json.dumps(payload, ensure_ascii=False))

    joined = "; ".join(exc.value.field_errors)
    assert "x_post" in joined
    assert "cta" in joined


def test_parse_manual_content_reports_wrong_type() -> None:
    payload = dict(VALID_CONTENT)
    payload["hashtags"] = "水筒"

    with pytest.raises(ManualContentParseError) as exc:
        parse_manual_content(json.dumps(payload, ensure_ascii=False))

    assert any("hashtags" in err for err in exc.value.field_errors)


def test_parse_manual_content_rejects_non_object() -> None:
    with pytest.raises(ManualContentParseError):
        parse_manual_content("[1, 2, 3]")


# --- API --------------------------------------------------------------------


def test_get_candidate_prompt_returns_agent_prompt(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v1", body=PROMPT_BODY)
    product = make_product(session, name="軽量ステンレスボトル")
    candidate = make_candidate(session, product)

    response = api_client.get(f"/api/v1/candidates/{candidate.id}/prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["prompt_version"] == "gen-v1"
    assert "軽量ステンレスボトル" in body["prompt"]
    assert body["prompt"] == build_generator_prompt(session, product)[0]


def test_get_candidate_prompt_returns_404_for_unknown_candidate(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    db_session_factory()
    response = api_client.get(f"/api/v1/candidates/{uuid.uuid4()}/prompt")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_manual_content_is_saved_as_needs_review_with_manual_source(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v1", body=PROMPT_BODY)
    product = make_product(session)
    candidate = make_candidate(session, product, selected_date=date(2026, 7, 22))

    response = api_client.post(
        f"/api/v1/candidates/{candidate.id}/manual-content",
        json={"content": _valid_json(), "prompt_version": "gen-v1"},
    )

    assert response.status_code == 200
    body = response.json()
    # LLM評価を行わないため evaluated ではなく needs_review で止める
    assert body["status"] == "needs_review"
    assert body["generation_source"] == "manual"
    assert body["prompt_version"] == "gen-v1"
    assert body["rule_violations"] == []

    session.expire_all()
    content = session.get(Content, uuid.UUID(body["content_id"]))
    assert content is not None
    assert content.status == "needs_review"
    assert content.generation_source == "manual"
    assert content.title == VALID_CONTENT["title"]


def test_manual_content_returns_rule_violations(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v1", body=PROMPT_BODY)
    product = make_product(session)
    candidate = make_candidate(session, product)

    payload = dict(VALID_CONTENT)
    payload["x_post"] = "今なら2980円でお得です"  # #ad 無し + 価格表記(ng_words)

    response = api_client.post(
        f"/api/v1/candidates/{candidate.id}/manual-content",
        json={"content": json.dumps(payload, ensure_ascii=False)},
    )

    assert response.status_code == 200
    violations = response.json()["rule_violations"]
    assert any("#ad" in v for v in violations)
    assert any("禁止表現" in v for v in violations)
    # 違反があっても保存はされ、レビュー画面で人が判断する
    assert response.json()["status"] == "needs_review"


def test_manual_content_returns_422_with_field_names(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v1", body=PROMPT_BODY)
    product = make_product(session)
    candidate = make_candidate(session, product)

    payload = dict(VALID_CONTENT)
    del payload["cta"]

    response = api_client.post(
        f"/api/v1/candidates/{candidate.id}/manual-content",
        json={"content": json.dumps(payload, ensure_ascii=False)},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "cta" in error["message"]


def test_manual_content_defaults_prompt_version_to_active(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_prompt_version(session, agent="generator", version="gen-v9", body=PROMPT_BODY)
    product = make_product(session)
    candidate = make_candidate(session, product)

    response = api_client.post(
        f"/api/v1/candidates/{candidate.id}/manual-content",
        json={"content": _valid_json()},
    )

    assert response.status_code == 200
    assert response.json()["prompt_version"] == "gen-v9"
