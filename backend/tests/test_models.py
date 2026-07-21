import uuid
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Candidate,
    Content,
    ImportErrorRecord,
    Job,
    LlmUsage,
    Product,
    ProductMetric,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_product_and_metric_roundtrip() -> None:
    session = _make_session()
    product = Product(
        item_code="shop1:0001",
        name="テスト商品",
        genre_id="100227",
        genre_name="スイーツ",
        shop_code="shop1",
        shop_name="テストショップ",
        item_url="https://item.rakuten.co.jp/shop1/0001/",
    )
    session.add(product)
    session.flush()

    metric = ProductMetric(
        product_id=product.id,
        snapshot_date=date(2026, 7, 21),
        price=1980,
        review_count=120,
        review_average=4.3,
        rank=3,
        rank_genre_id="100227",
    )
    session.add(metric)
    session.commit()

    fetched = session.get(Product, product.id)
    assert fetched is not None
    assert fetched.excluded is False
    assert len(fetched.metrics) == 1
    assert fetched.metrics[0].price == 1980


def test_candidate_content_and_job_chain() -> None:
    session = _make_session()
    product = Product(
        item_code="shop1:0002",
        name="テスト商品2",
        genre_id="100227",
        genre_name="スイーツ",
        shop_code="shop1",
        shop_name="テストショップ",
        item_url="https://item.rakuten.co.jp/shop1/0002/",
    )
    session.add(product)
    session.flush()

    candidate = Candidate(
        product_id=product.id,
        selected_date=date(2026, 7, 21),
        score=0.82,
        score_breakdown={"rank_trend": 0.5, "review_growth": 0.3},
    )
    session.add(candidate)
    session.flush()

    content = Content(
        product_id=product.id,
        candidate_id=candidate.id,
        title="タイトル",
        description="説明文",
        hashtags=["#楽天ROOM", "#スイーツ"],
        x_post="Xの投稿文 #ad",
        cta="今すぐチェック",
        prompt_version="gen-v1",
    )
    session.add(content)

    job = Job(pipeline="daily", step="generate", status="running")
    session.add(job)
    session.flush()

    usage = LlmUsage(
        job_id=job.id,
        agent="generator",
        model="claude-sonnet-5",
        input_tokens=500,
        output_tokens=200,
        estimated_cost_jpy=1.2,
    )
    session.add(usage)

    error = ImportErrorRecord(raw_line="broken,row", reason="itemCode not found")
    session.add(error)
    session.commit()

    assert content.status == "draft"
    assert content.regen_count == 0
    assert isinstance(content.id, uuid.UUID)
    assert job.status == "running"
