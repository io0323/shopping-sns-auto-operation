import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.research import GenreConfig, PriceBand, StrategyConfig
from app.agents.selection import ScoringWeights, SeasonalityConfig
from app.clients.llm import LlmResult
from app.clients.rakuten_api import RakutenItem
from app.harness.cost_guard import BudgetExceededError
from app.harness.job_queue import (
    PipelineAlreadyRunningError,
    finish_step,
    get_step_job,
    start_step,
)
from app.harness.pipeline import run_daily_pipeline
from app.models import (
    Base,
    Candidate,
    Content,
    Job,
    Product,
    ProductMetric,
    PromptVersion,
)

GENRE_ID = "999999"
PRICE_BAND = PriceBand(min=1000, max=10000, soft_min=500, soft_max=15000)
STRATEGY = StrategyConfig(
    genres=[GenreConfig(id=GENRE_ID, name="テストジャンル")],
    daily_candidate_count=10,
    price_band=PRICE_BAND,
)
WEIGHTS = ScoringWeights(
    rank_trend=0.25,
    review_growth=0.20,
    rating=0.15,
    seasonality=0.15,
    price_fit=0.15,
    competition=0.10,
)
SEASONALITY = SeasonalityConfig(default=0.5, genres={})


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


def _seed_baseline_products_and_metrics(
    session: Session, run_date: date, count: int
) -> list[Product]:
    baseline_date = run_date - timedelta(days=6)
    products = []
    for i in range(count):
        product = Product(
            item_code=f"shop1:{i:04d}",
            name=f"商品{i}",
            genre_id=GENRE_ID,
            genre_name="テストジャンル",
            shop_code="shop1",
            shop_name="ショップ",
            item_url=f"https://item.rakuten.co.jp/shop1/{i:04d}/",
        )
        session.add(product)
        session.flush()
        session.add(
            ProductMetric(
                product_id=product.id,
                snapshot_date=baseline_date,
                price=3000,
                review_count=100,
                review_average=4.0,
                rank=15,
                rank_genre_id=GENRE_ID,
            )
        )
        products.append(product)
    session.commit()
    return products


def _build_today_items(count: int) -> list[RakutenItem]:
    items = []
    for i in range(count):
        items.append(
            RakutenItem.model_validate(
                {
                    "itemCode": f"shop1:{i:04d}",
                    "itemName": f"商品{i}",
                    "itemPrice": 3000,
                    "itemUrl": f"https://item.rakuten.co.jp/shop1/{i:04d}/",
                    "affiliateUrl": f"https://hb.afl.rakuten.co.jp/shop1/{i:04d}/",
                    "shopCode": "shop1",
                    "shopName": "ショップ",
                    "genreId": GENRE_ID,
                    "reviewCount": 100,
                    "reviewAverage": round(3.6 + i * 0.12, 2),
                    "pointRate": 1,
                    "mediumImageUrls": [{"imageUrl": "https://image.example/1.jpg"}],
                    "rank": 15,
                }
            )
        )
    return items


class FakeRakutenClient:
    def __init__(self, items: list[RakutenItem]) -> None:
        self._items = items
        self.calls = 0

    def get_ranking(self, genre_id: str, page: int = 1) -> list[RakutenItem]:
        self.calls += 1
        return self._items

    def search_items(
        self, genre_id: str, hits: int = 30, sort: str = "-reviewCount", page: int = 1
    ) -> list[RakutenItem]:
        return self._items


def _content_json(index: int) -> str:
    return json.dumps(
        {
            "title": f"おすすめ商品{index}",
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


class FakeLlmClient:
    def __init__(self, generator_responses: list[str], evaluator_responses: list[str]) -> None:
        self._generator_responses = iter(generator_responses)
        self._evaluator_responses = iter(evaluator_responses)
        self.generator_calls = 0
        self.evaluator_calls = 0

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
            text = next(self._generator_responses)
        else:
            self.evaluator_calls += 1
            text = next(self._evaluator_responses)
        return LlmResult(text=text, input_tokens=10, output_tokens=10, estimated_cost_jpy=0.0)


def test_run_daily_pipeline_produces_ten_evaluated_candidates() -> None:
    session = _make_session()
    _seed_prompts(session)
    run_date = date(2026, 7, 21)
    _seed_baseline_products_and_metrics(session, run_date, count=12)

    fake_rakuten = FakeRakutenClient(_build_today_items(12))
    fake_llm = FakeLlmClient(
        generator_responses=[_content_json(i) for i in range(10)],
        evaluator_responses=[_eval_json_pass() for _ in range(10)],
    )

    result = run_daily_pipeline(
        session,
        run_date=run_date,
        rakuten_client=fake_rakuten,
        llm_client=fake_llm,
        strategy=STRATEGY,
        weights=WEIGHTS,
        seasonality=SEASONALITY,
    )

    assert result["selection"]["candidates"] == 10
    assert result["generate"]["candidates"] == 10
    assert result["generate"]["generated"] == 10
    assert result["generate"]["needs_review"] == 0
    assert result["generate"]["failed"] == 0
    assert result["generate"]["budget_exceeded"] is False
    assert result["save"] == {"total": 10, "evaluated": 10, "needs_review": 0}
    assert "候補10件" in result["notify"]["message"]

    candidates = session.execute(select(Candidate)).scalars().all()
    assert len(candidates) == 10
    assert all(c.status == "generated" for c in candidates)

    contents = session.execute(select(Content)).scalars().all()
    assert len(contents) == 10
    assert all(c.status == "evaluated" for c in contents)

    jobs = session.execute(select(Job)).scalars().all()
    steps_done = {j.step for j in jobs if j.status == "done"}
    assert steps_done == {"research", "selection", "generate", "save", "notify"}


def test_run_daily_pipeline_raises_when_already_running() -> None:
    session = _make_session()
    _seed_prompts(session)
    session.add(Job(pipeline="daily", step="research", status="running"))
    session.commit()

    with pytest.raises(PipelineAlreadyRunningError):
        run_daily_pipeline(
            session,
            run_date=date(2026, 7, 21),
            rakuten_client=FakeRakutenClient([]),
            llm_client=FakeLlmClient([], []),
        )


def test_run_daily_pipeline_skips_already_completed_steps() -> None:
    session = _make_session()
    _seed_prompts(session)
    run_date = date(2026, 7, 21)

    research_job = start_step(session, "daily", "research", run_date)
    finish_step(session, research_job, status="done", result={"genres": 1})
    selection_job = start_step(session, "daily", "selection", run_date)
    finish_step(session, selection_job, status="done", result={"candidates": 0})

    fake_rakuten = FakeRakutenClient([])
    fake_llm = FakeLlmClient([], [])

    result = run_daily_pipeline(
        session,
        run_date=run_date,
        rakuten_client=fake_rakuten,
        llm_client=fake_llm,
        strategy=STRATEGY,
        weights=WEIGHTS,
        seasonality=SEASONALITY,
    )

    assert fake_rakuten.calls == 0
    assert result["research"] == {"genres": 1}
    assert result["selection"] == {"candidates": 0}
    assert get_step_job(session, "daily", "research", run_date) is not None


def test_generate_step_stops_when_budget_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    _seed_prompts(session)
    run_date = date(2026, 7, 21)

    research_job = start_step(session, "daily", "research", run_date)
    finish_step(session, research_job, status="done", result={})
    selection_job = start_step(session, "daily", "selection", run_date)
    finish_step(session, selection_job, status="done", result={})

    product = Product(
        item_code="shop1:0000",
        name="商品0",
        genre_id=GENRE_ID,
        genre_name="テストジャンル",
        shop_code="shop1",
        shop_name="ショップ",
        item_url="https://item.rakuten.co.jp/shop1/0000/",
    )
    session.add(product)
    session.flush()
    session.add(
        Candidate(
            product_id=product.id,
            selected_date=run_date,
            score=0.9,
            score_breakdown={"rank_trend": 0.5},
            status="selected",
        )
    )
    session.commit()

    def _raise_budget_exceeded(_session: Session) -> None:
        raise BudgetExceededError("budget exceeded")

    monkeypatch.setattr("app.harness.pipeline.check_budget", _raise_budget_exceeded)

    fake_llm = FakeLlmClient([], [])

    result = run_daily_pipeline(
        session,
        run_date=run_date,
        rakuten_client=FakeRakutenClient([]),
        llm_client=fake_llm,
        strategy=STRATEGY,
        weights=WEIGHTS,
        seasonality=SEASONALITY,
    )

    assert result["generate"]["budget_exceeded"] is True
    assert result["generate"]["generated"] == 0
    assert fake_llm.generator_calls == 0
    assert "予算上限" in result["notify"]["message"]
