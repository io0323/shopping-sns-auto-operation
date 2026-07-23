import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.clients.llm import LlmResult
from app.harness.job_queue import PipelineAlreadyRunningError, finish_step, start_step
from app.harness.pipeline import run_weekly_pipeline
from app.models import Base, Candidate, Content, Job, Product, PromptVersion, Result


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_prompts(session: Session) -> None:
    session.add(
        PromptVersion(agent="generator", version="gen-v1", body="現行プロンプト", is_active=True)
    )
    session.add(
        PromptVersion(
            agent="learning",
            version="learning-v1",
            body="{data_point_count} {high_group_json} {low_group_json} {current_generator_prompt}",
            is_active=True,
        )
    )
    session.commit()


def _seed_datapoint(session: Session, index: int, revenue: int) -> None:
    product = Product(
        item_code=f"shop1:{index:04d}",
        name=f"商品{index}",
        genre_id="100",
        genre_name="ジャンルA",
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
        status="posted",
        posted_at=datetime(2026, 7, 5, 12, 0),
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


LEARNING_RESPONSE = (
    '{"report": {"summary": "s", "high_performer_patterns": [], '
    '"low_performer_patterns": [], "recommendations": []}, '
    '"proposed_generator_prompt": "新プロンプト", "rationale": "根拠"}'
)


class FakeLlmClient:
    def complete(
        self, *, job_id: uuid.UUID, agent: str, model: str, prompt: str, max_tokens: int = 1024
    ) -> LlmResult:
        return LlmResult(
            text=LEARNING_RESPONSE, input_tokens=10, output_tokens=10, estimated_cost_jpy=0.0
        )


def test_run_weekly_pipeline_insufficient_data_skips_learning() -> None:
    session = _make_session()
    _seed_prompts(session)
    run_date = date(2026, 7, 26)

    result = run_weekly_pipeline(session, run_date=run_date, llm_client=FakeLlmClient())

    assert result["learning"]["status"] == "insufficient_data"
    assert "スキップ" in result["notify"]["message"]

    jobs = session.execute(select(Job)).scalars().all()
    steps_done = {j.step for j in jobs if j.status == "done"}
    assert steps_done == {"learning", "notify"}


def test_run_weekly_pipeline_completes_and_creates_proposal() -> None:
    session = _make_session()
    _seed_prompts(session)
    for i in range(30):
        revenue = 1000 if i % 2 == 0 else 100
        _seed_datapoint(session, i, revenue=revenue)
    run_date = date(2026, 7, 26)

    result = run_weekly_pipeline(session, run_date=run_date, llm_client=FakeLlmClient())

    assert result["learning"]["status"] == "completed"
    assert result["learning"]["proposed_prompt_version"] == "gen-v2"
    assert "gen-v2" in result["notify"]["message"]

    proposed = session.execute(
        select(PromptVersion).where(
            PromptVersion.agent == "generator", PromptVersion.version == "gen-v2"
        )
    ).scalar_one()
    assert proposed.is_active is False


def test_run_weekly_pipeline_raises_when_already_running() -> None:
    session = _make_session()
    _seed_prompts(session)
    session.add(Job(pipeline="weekly", step="learning", status="running"))
    session.commit()

    with pytest.raises(PipelineAlreadyRunningError):
        run_weekly_pipeline(session, run_date=date(2026, 7, 26), llm_client=FakeLlmClient())


def test_run_weekly_pipeline_skips_already_completed_learning_step() -> None:
    session = _make_session()
    _seed_prompts(session)
    run_date = date(2026, 7, 26)

    learning_job = start_step(session, "weekly", "learning", run_date)
    finish_step(
        session,
        learning_job,
        status="done",
        result={
            "status": "insufficient_data",
            "data_point_count": 5,
            "report": None,
            "proposed_prompt_version_id": None,
            "proposed_prompt_version": None,
        },
    )

    class UnusedLlmClient:
        def complete(self, **kwargs: object) -> LlmResult:
            raise AssertionError("LLM should not be called")

    result = run_weekly_pipeline(
        session, run_date=run_date, llm_client=UnusedLlmClient()  # type: ignore[arg-type]
    )

    assert result["learning"]["data_point_count"] == 5
