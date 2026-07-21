import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.evaluator import NgWordsConfig, rule_check, run_generate_and_evaluate
from app.agents.generator import GeneratedContent
from app.clients.llm import LlmResult
from app.models import Base, Candidate, Product, PromptVersion


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_prompts(session: Session) -> None:
    session.add(
        PromptVersion(agent="generator", version="gen-v1", body="{product_json}", is_active=True)
    )
    session.add(
        PromptVersion(
            agent="evaluator",
            version="eval-v1",
            body="{content_json} {recent_posts}",
            is_active=True,
        )
    )
    session.commit()


def _add_product_and_candidate(session: Session) -> tuple[Product, Candidate]:
    product = Product(
        item_code="shop1:0001",
        name="テスト商品",
        genre_id="100283",
        genre_name="スイーツ",
        shop_code="shop1",
        shop_name="ショップ",
        item_url="https://item.rakuten.co.jp/x/",
    )
    session.add(product)
    session.flush()
    candidate = Candidate(
        product_id=product.id,
        selected_date=date(2026, 7, 21),
        score=0.8,
        score_breakdown={"rank_trend": 0.5},
    )
    session.add(candidate)
    session.flush()
    return product, candidate


def _content_json(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "title": "かわいい新作コスメ",
        "description": "あ" * 100,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "x_post": "投稿テキスト #ad",
        "cta": "今すぐチェック",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def _eval_json(total: int, improvement: str | None = None) -> str:
    verdict = "pass" if total >= 80 else "fail"
    axis = total // 5
    return json.dumps(
        {
            "total": total,
            "scores": {
                "natural": axis,
                "readability": axis,
                "appeal": axis,
                "uniqueness": axis,
                "compliance": axis,
            },
            "verdict": verdict,
            "improvement": improvement,
        },
        ensure_ascii=False,
    )


class FakeLlmClient:
    def __init__(self, generator_responses: list[str], evaluator_responses: list[str]) -> None:
        self._generator_responses = iter(generator_responses)
        self._evaluator_responses = iter(evaluator_responses)
        self.generator_calls = 0
        self.evaluator_calls = 0
        self.generator_prompts: list[str] = []

    def complete(
        self,
        *,
        job_id: uuid.UUID,
        agent: str,
        model: str,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LlmResult:
        if agent == "generator":
            self.generator_calls += 1
            self.generator_prompts.append(prompt)
            text = next(self._generator_responses)
        else:
            self.evaluator_calls += 1
            text = next(self._evaluator_responses)
        return LlmResult(text=text, input_tokens=10, output_tokens=10, estimated_cost_jpy=0.0)


def test_rule_check_detects_missing_ad_tag() -> None:
    content = GeneratedContent.model_validate(json.loads(_content_json(x_post="投稿テキスト")))
    violations = rule_check(content, NgWordsConfig(patterns=[]))
    assert any("#ad" in v for v in violations)


def test_rule_check_detects_ng_word() -> None:
    content = GeneratedContent.model_validate(
        json.loads(_content_json(description="これは最強の商品です" + "あ" * 90))
    )
    violations = rule_check(content, NgWordsConfig(patterns=["最強"]))
    assert any("禁止表現" in v for v in violations)


def test_rule_check_detects_length_violation() -> None:
    content = GeneratedContent.model_validate(json.loads(_content_json(cta="あ" * 21)))
    violations = rule_check(content, NgWordsConfig(patterns=[]))
    assert any("cta" in v for v in violations)


def test_rule_check_passes_clean_content() -> None:
    content = GeneratedContent.model_validate(json.loads(_content_json()))
    assert rule_check(content, NgWordsConfig(patterns=["最強"])) == []


def test_run_generate_and_evaluate_passes_on_first_attempt() -> None:
    session = _make_session()
    _seed_prompts(session)
    product, candidate = _add_product_and_candidate(session)

    llm_client = FakeLlmClient(
        generator_responses=[_content_json()],
        evaluator_responses=[_eval_json(85)],
    )

    content = run_generate_and_evaluate(session, llm_client, uuid.uuid4(), product, candidate)

    assert content.status == "evaluated"
    assert content.quality_score == 85.0
    assert content.regen_count == 0
    assert llm_client.generator_calls == 1
    assert llm_client.evaluator_calls == 1


def test_run_generate_and_evaluate_needs_review_after_max_attempts() -> None:
    session = _make_session()
    _seed_prompts(session)
    product, candidate = _add_product_and_candidate(session)

    llm_client = FakeLlmClient(
        generator_responses=[_content_json(), _content_json(), _content_json()],
        evaluator_responses=[
            _eval_json(50, "もっと具体的に"),
            _eval_json(50, "もっと具体的に"),
            _eval_json(50, "もっと具体的に"),
        ],
    )

    content = run_generate_and_evaluate(session, llm_client, uuid.uuid4(), product, candidate)

    assert content.status == "needs_review"
    assert content.quality_score == 50.0
    assert content.regen_count == 2
    assert llm_client.generator_calls == 3
    assert llm_client.evaluator_calls == 3


def test_run_generate_and_evaluate_feeds_eval_improvement_into_next_prompt() -> None:
    session = _make_session()
    _seed_prompts(session)
    product, candidate = _add_product_and_candidate(session)

    llm_client = FakeLlmClient(
        generator_responses=[_content_json(), _content_json()],
        evaluator_responses=[_eval_json(50, "もっと具体的に描写してください"), _eval_json(90)],
    )

    content = run_generate_and_evaluate(session, llm_client, uuid.uuid4(), product, candidate)

    assert content.status == "evaluated"
    assert llm_client.generator_calls == 2
    # 1回目のLLM評価で受け取ったimprovementが2回目のgeneratorプロンプトに反映されていること
    assert "もっと具体的に描写してください" not in llm_client.generator_prompts[0]
    assert "もっと具体的に描写してください" in llm_client.generator_prompts[1]


def test_run_generate_and_evaluate_regenerates_on_rule_violation_without_evaluating() -> None:
    session = _make_session()
    _seed_prompts(session)
    product, candidate = _add_product_and_candidate(session)

    llm_client = FakeLlmClient(
        generator_responses=[_content_json(x_post="投稿テキスト"), _content_json()],
        evaluator_responses=[_eval_json(90)],
    )

    content = run_generate_and_evaluate(session, llm_client, uuid.uuid4(), product, candidate)

    assert content.status == "evaluated"
    assert llm_client.generator_calls == 2
    assert llm_client.evaluator_calls == 1
