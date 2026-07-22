from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import ProductMetric
from tests.conftest import make_candidate, make_product


def test_list_products_returns_all(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_product(session, item_code="shop1:0001", name="商品A")
    make_product(session, item_code="shop1:0002", name="商品B")
    session.close()

    response = api_client.get("/api/v1/products")
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    assert len(body["items"]) == 2


def test_list_products_filters_by_genre_id(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_product(session, item_code="shop1:0001", genre_id="100283")
    make_product(session, item_code="shop1:0002", genre_id="100371")
    session.close()

    response = api_client.get("/api/v1/products", params={"genre_id": "100283"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["genre_id"] == "100283"


def test_list_products_filters_by_excluded(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_product(session, item_code="shop1:0001", excluded=True)
    make_product(session, item_code="shop1:0002", excluded=False)
    session.close()

    response = api_client.get("/api/v1/products", params={"excluded": "true"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["excluded"] is True


def test_list_products_min_score_filters_via_candidate_join(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    high = make_product(session, item_code="shop1:0001")
    low = make_product(session, item_code="shop1:0002")
    make_candidate(session, high, score=0.9)
    make_candidate(session, low, score=0.1)
    session.close()

    response = api_client.get("/api/v1/products", params={"min_score": 0.5})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["item_code"] == "shop1:0001"


def test_get_product_metrics_ordered_by_date(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    product = make_product(session)
    session.add(
        ProductMetric(
            product_id=product.id,
            snapshot_date=date(2026, 7, 20),
            price=2000,
            review_count=100,
            review_average=4.0,
            rank=10,
            rank_genre_id="100283",
        )
    )
    session.add(
        ProductMetric(
            product_id=product.id,
            snapshot_date=date(2026, 7, 21),
            price=2100,
            review_count=110,
            review_average=4.1,
            rank=8,
            rank_genre_id="100283",
        )
    )
    session.commit()
    product_id = product.id
    session.close()

    response = api_client.get(f"/api/v1/products/{product_id}/metrics")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["snapshot_date"] == "2026-07-20"
    assert body[1]["snapshot_date"] == "2026-07-21"


def test_get_product_metrics_404_when_product_missing(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/products/00000000-0000-0000-0000-000000000000/metrics")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
