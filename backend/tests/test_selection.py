from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.research import GenreConfig, PriceBand, StrategyConfig
from app.agents.selection import (
    ScoringWeights,
    SeasonalityConfig,
    clip,
    compute_competition,
    compute_price_fit,
    compute_rank_trend,
    compute_rating,
    compute_review_growth,
    run_daily_selection,
)
from app.models import Base, Candidate, Content, Product, ProductMetric

PRICE_BAND = PriceBand(min=1000, max=10000, soft_min=500, soft_max=15000)


def test_clip_bounds() -> None:
    assert clip(-0.5) == 0.0
    assert clip(1.5) == 1.0
    assert clip(0.3) == 0.3


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (400, 0.0),
        (500, 0.0),
        (750, 0.5),
        (1000, 1.0),
        (5000, 1.0),
        (10000, 1.0),
        (12500, 0.5),
        (15000, 0.0),
        (20000, 0.0),
    ],
)
def test_compute_price_fit(price: int, expected: float) -> None:
    assert compute_price_fit(price, PRICE_BAND) == pytest.approx(expected)


def test_compute_rank_trend_normal_and_clipped() -> None:
    assert compute_rank_trend(rank_baseline=40, rank_latest=10) == pytest.approx(1.0)
    assert compute_rank_trend(rank_baseline=20, rank_latest=10) == pytest.approx(10 / 30)
    assert compute_rank_trend(rank_baseline=10, rank_latest=20) == 0.0


def test_compute_rank_trend_missing_data_is_neutral() -> None:
    assert compute_rank_trend(None, 10) == 0.0
    assert compute_rank_trend(10, None) == 0.0
    assert compute_rank_trend(None, None) == 0.0


def test_compute_review_growth() -> None:
    assert compute_review_growth(100, 120) == pytest.approx(1.0)
    assert compute_review_growth(100, 110) == pytest.approx(0.5)
    assert compute_review_growth(100, 90) == 0.0


def test_compute_rating() -> None:
    assert compute_rating(3.5) == 0.0
    assert compute_rating(5.0) == pytest.approx(1.0)
    assert compute_rating(4.25) == pytest.approx(0.5)
    assert compute_rating(2.0) == 0.0


def test_compute_competition() -> None:
    assert compute_competition(0) == 0.0
    assert compute_competition(5000) == pytest.approx(0.5)
    assert compute_competition(20000) == 1.0


def test_scoring_weights_requires_sum_to_one() -> None:
    ScoringWeights(
        rank_trend=0.25,
        review_growth=0.20,
        rating=0.15,
        seasonality=0.15,
        price_fit=0.15,
        competition=0.10,
    )
    with pytest.raises(ValidationError):
        ScoringWeights(
            rank_trend=0.5,
            review_growth=0.20,
            rating=0.15,
            seasonality=0.15,
            price_fit=0.15,
            competition=0.10,
        )


def test_seasonality_default_fallback() -> None:
    config = SeasonalityConfig(default=0.4, genres={"100283": {"2": 0.9}})
    assert config.coefficient("100283", 2) == 0.9
    assert config.coefficient("100283", 3) == 0.4
    assert config.coefficient("999999", 1) == 0.4


WEIGHTS = ScoringWeights(
    rank_trend=0.25,
    review_growth=0.20,
    rating=0.15,
    seasonality=0.15,
    price_fit=0.15,
    competition=0.10,
)
SEASONALITY = SeasonalityConfig(default=0.5, genres={})
STRATEGY = StrategyConfig(
    genres=[GenreConfig(id="100283", name="スイーツ")],
    daily_candidate_count=2,
    price_band=PRICE_BAND,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_product(
    session: Session, item_code: str, genre_id: str = "100283", excluded: bool = False
) -> Product:
    product = Product(
        item_code=item_code,
        name=f"商品{item_code}",
        genre_id=genre_id,
        genre_name="スイーツ",
        shop_code="shop1",
        shop_name="ショップ",
        item_url="https://item.rakuten.co.jp/shop1/x/",
        excluded=excluded,
    )
    session.add(product)
    session.flush()
    return product


def _add_metric(
    session: Session,
    product: Product,
    snapshot_date: date,
    *,
    price: int = 2000,
    review_count: int = 100,
    review_average: float = 4.0,
    rank: int | None = 10,
) -> ProductMetric:
    metric = ProductMetric(
        product_id=product.id,
        snapshot_date=snapshot_date,
        price=price,
        review_count=review_count,
        review_average=review_average,
        rank=rank,
        rank_genre_id=product.genre_id,
    )
    session.add(metric)
    session.flush()
    return metric


def test_run_daily_selection_applies_exclusions_and_ranks_top_n() -> None:
    session = _make_session()
    today = date(2026, 7, 21)

    excluded_product = _add_product(session, "shop1:excluded", excluded=True)
    _add_metric(session, excluded_product, today - timedelta(days=6), review_count=50, rank=30)
    _add_metric(session, excluded_product, today, review_count=200, rank=5)

    posted_product = _add_product(session, "shop1:posted")
    _add_metric(session, posted_product, today - timedelta(days=6), review_count=50, rank=30)
    _add_metric(session, posted_product, today, review_count=200, rank=5)
    posted_candidate = Candidate(
        product_id=posted_product.id,
        selected_date=today - timedelta(days=10),
        score=0.5,
        score_breakdown={
            "rank_trend": 0,
            "review_growth": 0,
            "rating": 0,
            "seasonality": 0,
            "price_fit": 0,
            "competition": 0,
        },
        status="generated",
    )
    session.add(posted_candidate)
    session.flush()
    session.add(
        Content(
            product_id=posted_product.id,
            candidate_id=posted_candidate.id,
            title="t",
            description="d",
            hashtags=[],
            x_post="x",
            cta="c",
            prompt_version="gen-v1",
            status="posted",
            posted_at=datetime.combine(today - timedelta(days=10), datetime.min.time()),
        )
    )

    thin_product = _add_product(session, "shop1:thin")
    _add_metric(session, thin_product, today, review_count=200, rank=5)

    weak_product = _add_product(session, "shop1:weak")
    _add_metric(session, weak_product, today - timedelta(days=6), review_count=100, rank=10)
    _add_metric(
        session, weak_product, today, review_count=100, rank=10, review_average=3.0, price=100
    )

    strong_product = _add_product(session, "shop1:strong")
    _add_metric(session, strong_product, today - timedelta(days=6), review_count=50, rank=40)
    _add_metric(
        session, strong_product, today, review_count=200, rank=5, review_average=4.8, price=3000
    )

    mid_product = _add_product(session, "shop1:mid")
    _add_metric(session, mid_product, today - timedelta(days=6), review_count=80, rank=20)
    _add_metric(
        session, mid_product, today, review_count=110, rank=15, review_average=4.2, price=3000
    )

    session.commit()

    candidates = run_daily_selection(
        session, run_date=today, strategy=STRATEGY, weights=WEIGHTS, seasonality=SEASONALITY
    )

    assert len(candidates) == 2
    selected_products = {c.product_id for c in candidates}
    assert excluded_product.id not in selected_products
    assert posted_product.id not in selected_products
    assert thin_product.id not in selected_products
    assert weak_product.id not in selected_products
    assert strong_product.id in selected_products
    assert mid_product.id in selected_products

    for candidate in candidates:
        assert set(candidate.score_breakdown.keys()) == {
            "rank_trend",
            "review_growth",
            "rating",
            "seasonality",
            "price_fit",
            "competition",
        }
        assert candidate.status == "selected"
        assert candidate.selected_date == today

    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_run_daily_selection_returns_empty_when_no_eligible_products() -> None:
    session = _make_session()
    candidates = run_daily_selection(
        session,
        run_date=date(2026, 7, 21),
        strategy=STRATEGY,
        weights=WEIGHTS,
        seasonality=SEASONALITY,
    )
    assert candidates == []
