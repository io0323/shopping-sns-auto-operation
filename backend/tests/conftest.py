from collections.abc import Generator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.db as db_module
from app.main import app
from app.models import Base, Candidate, Content, Product


@pytest.fixture
def db_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    original_engine = db_module._engine
    original_factory = db_module._SessionLocal
    db_module._engine = engine
    db_module._SessionLocal = session_factory

    yield session_factory

    db_module._engine = original_engine
    db_module._SessionLocal = original_factory
    engine.dispose()


@pytest.fixture
def api_client(db_session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def make_product(session: Session, **overrides: Any) -> Product:
    defaults: dict[str, Any] = {
        "item_code": "shop1:0001",
        "name": "テスト商品",
        "genre_id": "100283",
        "genre_name": "スイーツ",
        "shop_code": "shop1",
        "shop_name": "ショップ",
        "item_url": "https://item.rakuten.co.jp/shop1/0001/",
    }
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.commit()
    return product


def make_candidate(session: Session, product: Product, **overrides: Any) -> Candidate:
    defaults: dict[str, Any] = {
        "product_id": product.id,
        "selected_date": date(2026, 7, 22),
        "score": 0.8,
        "score_breakdown": {"rank_trend": 0.5},
        "status": "selected",
    }
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def make_content(
    session: Session, product: Product, candidate: Candidate, **overrides: Any
) -> Content:
    defaults: dict[str, Any] = {
        "product_id": product.id,
        "candidate_id": candidate.id,
        "title": "タイトル",
        "description": "あ" * 100,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "x_post": "投稿テキスト #ad",
        "cta": "今すぐチェック",
        "prompt_version": "gen-v1",
        "status": "evaluated",
        "quality_score": 90.0,
        "quality_breakdown": {
            "natural": 18,
            "readability": 18,
            "appeal": 18,
            "uniqueness": 18,
            "compliance": 18,
        },
    }
    defaults.update(overrides)
    content = Content(**defaults)
    session.add(content)
    session.commit()
    return content
