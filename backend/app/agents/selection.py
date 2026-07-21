import math
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.research import CONFIG_DIR, PriceBand, StrategyConfig, load_strategy
from app.models import Candidate, Content, Product, ProductMetric

SCORING_PATH = CONFIG_DIR / "scoring.yaml"
SEASONALITY_PATH = CONFIG_DIR / "seasonality.yaml"

RECENT_METRICS_WINDOW_DAYS = 7
MIN_METRICS_DAYS = 2
RECENTLY_POSTED_WINDOW_DAYS = 30

SCORE_COMPONENT_NAMES = (
    "rank_trend",
    "review_growth",
    "rating",
    "seasonality",
    "price_fit",
    "competition",
)


class ScoringWeights(BaseModel):
    rank_trend: float
    review_growth: float
    rating: float
    seasonality: float
    price_fit: float
    competition: float

    @model_validator(mode="after")
    def _validate_sum_to_one(self) -> "ScoringWeights":
        total = sum(getattr(self, name) for name in SCORE_COMPONENT_NAMES)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")
        return self


class SeasonalityConfig(BaseModel):
    default: float = 0.5
    genres: dict[str, dict[str, float]] = Field(default_factory=dict)

    def coefficient(self, genre_id: str, month: int) -> float:
        return self.genres.get(genre_id, {}).get(str(month), self.default)


def load_scoring_weights(path: Path | None = None) -> ScoringWeights:
    target = path or SCORING_PATH
    with target.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ScoringWeights.model_validate(raw["weights"])


def load_seasonality(path: Path | None = None) -> SeasonalityConfig:
    target = path or SEASONALITY_PATH
    with target.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return SeasonalityConfig.model_validate(raw)


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def compute_price_fit(price: int, band: PriceBand) -> float:
    if price <= band.soft_min or price >= band.soft_max:
        return 0.0
    if price < band.min:
        return clip((price - band.soft_min) / (band.min - band.soft_min))
    if price <= band.max:
        return 1.0
    return clip((band.soft_max - price) / (band.soft_max - band.max))


def compute_rank_trend(rank_baseline: int | None, rank_latest: int | None) -> float:
    if rank_baseline is None or rank_latest is None:
        return 0.0
    return clip((rank_baseline - rank_latest) / 30)


def compute_review_growth(review_count_baseline: int, review_count_latest: int) -> float:
    return clip((review_count_latest - review_count_baseline) / 20)


def compute_rating(review_average: float) -> float:
    return clip((review_average - 3.5) / 1.5)


def compute_competition(review_count: int) -> float:
    return clip(review_count / 10000)


def compute_score_breakdown(
    baseline: ProductMetric,
    latest: ProductMetric,
    genre_id: str,
    price_band: PriceBand,
    seasonality: SeasonalityConfig,
    as_of: date,
) -> dict[str, float]:
    return {
        "rank_trend": compute_rank_trend(baseline.rank, latest.rank),
        "review_growth": compute_review_growth(baseline.review_count, latest.review_count),
        "rating": compute_rating(latest.review_average),
        "seasonality": clip(seasonality.coefficient(genre_id, as_of.month)),
        "price_fit": compute_price_fit(latest.price, price_band),
        "competition": compute_competition(latest.review_count),
    }


def compute_score(breakdown: dict[str, float], weights: ScoringWeights) -> float:
    return (
        weights.rank_trend * breakdown["rank_trend"]
        + weights.review_growth * breakdown["review_growth"]
        + weights.rating * breakdown["rating"]
        + weights.seasonality * breakdown["seasonality"]
        + weights.price_fit * breakdown["price_fit"]
        - weights.competition * breakdown["competition"]
    )


def _recent_metrics(session: Session, product_id: uuid.UUID, as_of: date) -> list[ProductMetric]:
    start = as_of - timedelta(days=RECENT_METRICS_WINDOW_DAYS - 1)
    stmt = (
        select(ProductMetric)
        .where(
            ProductMetric.product_id == product_id,
            ProductMetric.snapshot_date >= start,
            ProductMetric.snapshot_date <= as_of,
        )
        .order_by(ProductMetric.snapshot_date.asc())
    )
    return list(session.execute(stmt).scalars().all())


def _is_recently_posted(session: Session, product_id: uuid.UUID, as_of: date) -> bool:
    cutoff_date = as_of - timedelta(days=RECENTLY_POSTED_WINDOW_DAYS)
    cutoff = datetime.combine(cutoff_date, datetime.min.time())
    stmt = (
        select(Content.id)
        .where(
            Content.product_id == product_id,
            Content.status == "posted",
            Content.posted_at.is_not(None),
            Content.posted_at >= cutoff,
        )
        .limit(1)
    )
    return session.execute(stmt).first() is not None


def run_daily_selection(
    session: Session,
    run_date: date | None = None,
    strategy: StrategyConfig | None = None,
    weights: ScoringWeights | None = None,
    seasonality: SeasonalityConfig | None = None,
) -> list[Candidate]:
    run_date = run_date or date.today()
    strategy = strategy or load_strategy()
    weights = weights or load_scoring_weights()
    seasonality = seasonality or load_seasonality()

    scored: list[tuple[float, Product, dict[str, float]]] = []
    products = session.execute(select(Product).where(Product.excluded.is_(False))).scalars().all()

    for product in products:
        if _is_recently_posted(session, product.id, run_date):
            continue
        metrics = _recent_metrics(session, product.id, run_date)
        if len(metrics) < MIN_METRICS_DAYS:
            continue
        breakdown = compute_score_breakdown(
            metrics[0], metrics[-1], product.genre_id, strategy.price_band, seasonality, run_date
        )
        score = compute_score(breakdown, weights)
        scored.append((score, product, breakdown))

    scored.sort(key=lambda entry: entry[0], reverse=True)
    top = scored[: strategy.daily_candidate_count]

    candidates: list[Candidate] = []
    for score, product, breakdown in top:
        candidate = Candidate(
            product_id=product.id,
            selected_date=run_date,
            score=score,
            score_breakdown=breakdown,
            status="selected",
        )
        session.add(candidate)
        candidates.append(candidate)

    session.commit()
    return candidates
