import json
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.learning import (
    MIN_DATASET_SIZE,
    build_learning_dataset,
    run_learning,
    split_high_low_performers,
    summarize_group,
)
from app.clients.llm import LlmResult
from app.harness.cost_guard import BudgetExceededError
from app.models import Base, Candidate, Content, Job, Product, PromptVersion, Result


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_prompts(session: Session) -> None:
    session.add(
        PromptVersion(
            agent="generator", version="gen-v1", body="現行プロンプト本文", is_active=True
        )
    )
    session.add(
        PromptVersion(
            agent="learning",
            version="learning-v1",
            body=(
                "{data_point_count} {high_group_json} {low_group_json} "
                "{current_generator_prompt}"
            ),
            is_active=True,
        )
    )
    session.commit()


def _seed_datapoint(
    session: Session,
    index: int,
    revenue: int,
    genre_name: str = "ジャンルA",
    edited_by_human: bool = False,
    posted_at: datetime | None = None,
    status: str = "posted",
) -> None:
    product = Product(
        item_code=f"shop1:{index:04d}",
        name=f"商品{index}",
        genre_id="100",
        genre_name=genre_name,
        shop_code="shop1",
        shop_name="ショップ",
        item_url=f"https://item.example/{index}",
    )
    session.add(product)
    session.flush()

    candidate = Candidate(
        product_id=product.id,
        selected_date=date(2026, 7, 1),
        score=0.5,
        score_breakdown={"rank_trend": 0.5},
        status="generated",
    )
    session.add(candidate)
    session.flush()

    content = Content(
        product_id=product.id,
        candidate_id=candidate.id,
        title="タイトル",
        description="あ" * 100,
        hashtags=["#a", "#b", "#c"],
        x_post="投稿 #ad",
        cta="CTA",
        prompt_version="gen-v1",
        status=status,
        posted_at=posted_at if posted_at is not None else datetime(2026, 7, 5, 12, 0),
        edited_by_human=edited_by_human,
        quality_score=90.0,
        quality_breakdown={
            "natural": 18,
            "readability": 18,
            "appeal": 18,
            "uniqueness": 18,
            "compliance": 18,
        },
    )
    session.add(content)
    session.flush()

    session.add(
        Result(
            product_id=product.id,
            report_date_from=date(2026, 7, 1),
            report_date_to=date(2026, 7, 7),
            clicks=10,
            conversions=1,
            revenue=revenue,
        )
    )
    session.commit()


def test_build_learning_dataset_matches_posted_content_within_period() -> None:
    session = _make_session()
    _seed_datapoint(session, 0, revenue=1000)

    dataset = build_learning_dataset(session)

    assert len(dataset) == 1
    assert dataset[0].revenue == 1000
    assert dataset[0].genre_name == "ジャンルA"
    assert dataset[0].description_length == 100
    assert dataset[0].hashtag_count == 3
    assert dataset[0].quality_natural == 18
    assert dataset[0].candidate_score == 0.5


def test_build_learning_dataset_excludes_unposted_content() -> None:
    session = _make_session()
    _seed_datapoint(session, 0, revenue=1000, status="approved")

    dataset = build_learning_dataset(session)

    assert dataset == []


def test_build_learning_dataset_excludes_content_posted_outside_period() -> None:
    session = _make_session()
    _seed_datapoint(session, 0, revenue=1000, posted_at=datetime(2026, 8, 1))

    dataset = build_learning_dataset(session)

    assert dataset == []


def test_split_high_low_performers_orders_by_revenue() -> None:
    session = _make_session()
    for i in range(9):
        _seed_datapoint(session, i, revenue=(i + 1) * 100)

    dataset = build_learning_dataset(session)
    high, low = split_high_low_performers(dataset)

    assert len(high) == 3
    assert len(low) == 3
    assert all(p.revenue >= 700 for p in high)
    assert all(p.revenue <= 300 for p in low)


def test_summarize_group_aggregates_features() -> None:
    session = _make_session()
    _seed_datapoint(session, 0, revenue=100, genre_name="ジャンルA", edited_by_human=True)
    _seed_datapoint(session, 1, revenue=200, genre_name="ジャンルB", edited_by_human=False)

    dataset = build_learning_dataset(session)
    summary = summarize_group(dataset)

    assert summary["count"] == 2
    assert summary["avg_revenue"] == 150.0
    assert summary["edited_by_human_ratio"] == 0.5
    assert summary["genre_distribution"] == {"ジャンルA": 1, "ジャンルB": 1}


def test_run_learning_returns_insufficient_data_without_llm_call() -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(MIN_DATASET_SIZE - 1):
        _seed_datapoint(session, i, revenue=100)

    class UnusedLlmClient:
        def complete(self, **kwargs: object) -> LlmResult:
            raise AssertionError("LLM should not be called")

    result = run_learning(session, UnusedLlmClient(), uuid.uuid4())  # type: ignore[arg-type]

    assert result["status"] == "insufficient_data"
    assert result["data_point_count"] == MIN_DATASET_SIZE - 1
    generator_versions = session.execute(
        select(PromptVersion).where(PromptVersion.agent == "generator")
    ).scalars().all()
    assert len(generator_versions) == 1


def test_run_learning_returns_budget_exceeded_without_creating_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(MIN_DATASET_SIZE):
        _seed_datapoint(session, i, revenue=100)

    def _raise(_session: Session) -> None:
        raise BudgetExceededError("over budget")

    monkeypatch.setattr("app.agents.learning.check_budget", _raise)

    class UnusedLlmClient:
        def complete(self, **kwargs: object) -> LlmResult:
            raise AssertionError("LLM should not be called")

    result = run_learning(session, UnusedLlmClient(), uuid.uuid4())  # type: ignore[arg-type]

    assert result["status"] == "budget_exceeded"
    generator_versions = (
        session.execute(select(PromptVersion).where(PromptVersion.agent == "generator"))
        .scalars()
        .all()
    )
    assert len(generator_versions) == 1


def test_run_learning_creates_proposed_prompt_version() -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(MIN_DATASET_SIZE):
        revenue = 1000 if i % 2 == 0 else 100
        _seed_datapoint(session, i, revenue=revenue)

    response_text = json.dumps(
        {
            "report": {
                "summary": "高成果群は説明文が長い傾向",
                "high_performer_patterns": ["description長め"],
                "low_performer_patterns": ["hashtag数が少ない"],
                "recommendations": ["descriptionを詳しくする"],
            },
            "proposed_generator_prompt": "改善後のプロンプト本文",
            "rationale": "高成果群の特徴を反映",
        },
        ensure_ascii=False,
    )

    class FakeLlmClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(
            self, *, job_id: uuid.UUID, agent: str, model: str, prompt: str, max_tokens: int = 1024
        ) -> LlmResult:
            self.calls.append(agent)
            return LlmResult(
                text=response_text, input_tokens=10, output_tokens=10, estimated_cost_jpy=0.0
            )

    fake_llm = FakeLlmClient()
    job = Job(pipeline="weekly", step="learning", status="running")
    session.add(job)
    session.commit()
    job_id = job.id

    result = run_learning(session, fake_llm, job_id)  # type: ignore[arg-type]

    assert result["status"] == "completed"
    assert result["data_point_count"] == MIN_DATASET_SIZE
    assert result["proposed_prompt_version"] == "gen-v2"
    assert fake_llm.calls == ["learning"]

    proposed = session.execute(
        select(PromptVersion).where(
            PromptVersion.agent == "generator", PromptVersion.version == "gen-v2"
        )
    ).scalar_one()
    assert proposed.is_active is False
    assert proposed.body == "改善後のプロンプト本文"
    assert proposed.note == "高成果群の特徴を反映"


def test_run_learning_returns_invalid_llm_response_on_malformed_json() -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(MIN_DATASET_SIZE):
        _seed_datapoint(session, i, revenue=100)

    class MalformedLlmClient:
        def complete(
            self, *, job_id: uuid.UUID, agent: str, model: str, prompt: str, max_tokens: int = 1024
        ) -> LlmResult:
            return LlmResult(
                text="not json", input_tokens=10, output_tokens=10, estimated_cost_jpy=0.0
            )

    result = run_learning(session, MalformedLlmClient(), uuid.uuid4())  # type: ignore[arg-type]

    assert result["status"] == "invalid_llm_response"
    assert result["data_point_count"] == MIN_DATASET_SIZE
    generator_versions = (
        session.execute(select(PromptVersion).where(PromptVersion.agent == "generator"))
        .scalars()
        .all()
    )
    assert len(generator_versions) == 1


def test_run_learning_returns_invalid_llm_response_on_schema_mismatch() -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(MIN_DATASET_SIZE):
        _seed_datapoint(session, i, revenue=100)

    class SchemaMismatchLlmClient:
        def complete(
            self, *, job_id: uuid.UUID, agent: str, model: str, prompt: str, max_tokens: int = 1024
        ) -> LlmResult:
            return LlmResult(
                text=json.dumps({"unexpected": "shape"}),
                input_tokens=10,
                output_tokens=10,
                estimated_cost_jpy=0.0,
            )

    result = run_learning(session, SchemaMismatchLlmClient(), uuid.uuid4())  # type: ignore[arg-type]

    assert result["status"] == "invalid_llm_response"
