import logging
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.rakuten_api import RakutenApiClient, RakutenApiError, RakutenItem
from app.models import Product, ProductMetric

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
STRATEGY_PATH = CONFIG_DIR / "strategy.yaml"

RANKING_HITS = 30


class GenreConfig(BaseModel):
    id: str
    name: str


class PriceBand(BaseModel):
    min: int
    max: int
    soft_min: int
    soft_max: int


class StrategyConfig(BaseModel):
    genres: list[GenreConfig]
    daily_candidate_count: int = 10
    price_band: PriceBand


def load_strategy(path: Path | None = None) -> StrategyConfig:
    target = path or STRATEGY_PATH
    with target.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return StrategyConfig.model_validate(raw)


def upsert_product(session: Session, item: RakutenItem, genre_name: str) -> Product:
    product = session.execute(
        select(Product).where(Product.item_code == item.item_code)
    ).scalar_one_or_none()
    image_url = item.medium_image_urls[0].image_url if item.medium_image_urls else None
    item_url = item.affiliate_url or item.item_url

    if product is None:
        product = Product(
            item_code=item.item_code,
            name=item.item_name,
            genre_id=item.genre_id,
            genre_name=genre_name,
            shop_code=item.shop_code,
            shop_name=item.shop_name,
            item_url=item_url,
            image_url=image_url,
        )
        session.add(product)
    else:
        product.name = item.item_name
        product.genre_id = item.genre_id
        product.genre_name = genre_name
        product.shop_code = item.shop_code
        product.shop_name = item.shop_name
        product.item_url = item_url
        product.image_url = image_url

    session.flush()
    return product


def upsert_metric(
    session: Session,
    product: Product,
    item: RakutenItem,
    snapshot_date: date,
    rank_genre_id: str,
) -> ProductMetric:
    metric = session.execute(
        select(ProductMetric).where(
            ProductMetric.product_id == product.id,
            ProductMetric.snapshot_date == snapshot_date,
        )
    ).scalar_one_or_none()

    if metric is None:
        metric = ProductMetric(product_id=product.id, snapshot_date=snapshot_date)
        session.add(metric)

    metric.price = item.item_price
    metric.point_rate = item.point_rate
    metric.review_count = item.review_count
    metric.review_average = item.review_average
    metric.rank = item.rank
    metric.rank_genre_id = rank_genre_id

    session.flush()
    return metric


def run_daily_research(
    session: Session,
    client: RakutenApiClient,
    strategy: StrategyConfig | None = None,
    run_date: date | None = None,
) -> dict[str, int]:
    strategy = strategy or load_strategy()
    run_date = run_date or date.today()

    products_upserted = 0
    metrics_written = 0
    genres_failed = 0

    for genre in strategy.genres:
        try:
            items = client.get_ranking(genre_id=genre.id)[:RANKING_HITS]
        except RakutenApiError:
            logger.exception("failed to fetch ranking for genre_id=%s, skipping", genre.id)
            genres_failed += 1
            continue

        for item in items:
            product = upsert_product(session, item, genre.name)
            upsert_metric(session, product, item, run_date, genre.id)
            products_upserted += 1
            metrics_written += 1

    session.commit()
    return {
        "genres": len(strategy.genres),
        "genres_failed": genres_failed,
        "products": products_upserted,
        "metrics": metrics_written,
    }
