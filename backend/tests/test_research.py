from datetime import date
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.research import GenreConfig, StrategyConfig, load_strategy, run_daily_research
from app.clients.rakuten_api import RakutenApiError, RakutenItem
from app.models import Base, Product, ProductMetric

PRICE_BAND = {"min": 1000, "max": 10000, "soft_min": 500, "soft_max": 15000}


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _item(
    item_code: str = "shop1:0001", price: int = 1980, review_count: int = 100, rank: int = 5
) -> RakutenItem:
    return RakutenItem.model_validate(
        {
            "itemCode": item_code,
            "itemName": "テスト商品",
            "itemPrice": price,
            "itemUrl": "https://item.rakuten.co.jp/shop1/0001/",
            "affiliateUrl": "https://hb.afl.rakuten.co.jp/xxx",
            "shopCode": "shop1",
            "shopName": "テストショップ",
            "genreId": "100283",
            "reviewCount": review_count,
            "reviewAverage": 4.5,
            "pointRate": 1,
            "mediumImageUrls": [{"imageUrl": "https://image.example/1.jpg"}],
            "rank": rank,
        }
    )


def test_run_daily_research_upserts_products_and_metrics() -> None:
    session = _make_session()
    client = MagicMock()
    client.get_ranking.return_value = [_item()]
    strategy = StrategyConfig(
        genres=[GenreConfig(id="100283", name="スイーツ")], price_band=PRICE_BAND
    )

    result = run_daily_research(session, client, strategy=strategy, run_date=date(2026, 7, 21))

    assert result == {"genres": 1, "genres_failed": 0, "products": 1, "metrics": 1}

    product = session.execute(
        select(Product).where(Product.item_code == "shop1:0001")
    ).scalar_one()
    assert product.name == "テスト商品"
    assert product.genre_name == "スイーツ"
    assert product.item_url == "https://hb.afl.rakuten.co.jp/xxx"
    assert product.image_url == "https://image.example/1.jpg"

    metric = session.execute(
        select(ProductMetric).where(ProductMetric.product_id == product.id)
    ).scalar_one()
    assert metric.price == 1980
    assert metric.rank == 5
    assert metric.snapshot_date == date(2026, 7, 21)


def test_run_daily_research_same_day_rerun_is_idempotent() -> None:
    session = _make_session()
    client = MagicMock()
    strategy = StrategyConfig(
        genres=[GenreConfig(id="100283", name="スイーツ")], price_band=PRICE_BAND
    )
    run_date = date(2026, 7, 21)

    client.get_ranking.return_value = [_item(price=1980, review_count=100, rank=5)]
    run_daily_research(session, client, strategy=strategy, run_date=run_date)

    client.get_ranking.return_value = [_item(price=2500, review_count=150, rank=3)]
    run_daily_research(session, client, strategy=strategy, run_date=run_date)

    products = session.execute(select(Product)).scalars().all()
    assert len(products) == 1

    metrics = session.execute(select(ProductMetric)).scalars().all()
    assert len(metrics) == 1
    assert metrics[0].price == 2500
    assert metrics[0].review_count == 150
    assert metrics[0].rank == 3


def test_run_daily_research_skips_failing_genre_and_continues() -> None:
    session = _make_session()
    client = MagicMock()

    def get_ranking(genre_id: str, page: int = 1) -> list[RakutenItem]:
        if genre_id == "bad":
            raise RakutenApiError("boom")
        return [_item(item_code="shop1:ok")]

    client.get_ranking.side_effect = get_ranking

    strategy = StrategyConfig(
        genres=[
            GenreConfig(id="bad", name="失敗ジャンル"),
            GenreConfig(id="100283", name="スイーツ"),
        ],
        price_band=PRICE_BAND,
    )

    result = run_daily_research(session, client, strategy=strategy, run_date=date(2026, 7, 21))

    assert result["genres"] == 2
    assert result["genres_failed"] == 1
    assert result["products"] == 1


def test_load_strategy_parses_sample_config() -> None:
    strategy = load_strategy()
    assert len(strategy.genres) > 0
    assert strategy.daily_candidate_count > 0
    assert strategy.price_band.min < strategy.price_band.max
