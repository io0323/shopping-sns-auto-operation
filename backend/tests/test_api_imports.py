from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import make_product

CSV_HEADER = "itemCode,商品URL,集計期間(開始),集計期間(終了),クリック数,成果件数,成果報酬額"


def _upload(api_client: TestClient, csv_text: str) -> Response:
    files = {"file": ("report.csv", csv_text.encode("cp932"), "text/csv")}
    return api_client.post("/api/v1/import/affiliate-csv", files=files)


def test_import_affiliate_csv_endpoint_returns_summary(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    session = db_session_factory()
    make_product(session, item_code="shop1:0001")
    session.close()

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop1:0001,,2026-07-01,2026-07-07,10,1,100",
            "shop9:9999,,2026-07-01,2026-07-07,10,1,100",
        ]
    )

    response = _upload(api_client, csv_text)
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 1
    assert body["updated"] == 0
    assert body["error_count"] == 1
    assert len(body["errors"]) == 1


def test_import_affiliate_csv_endpoint_rejects_invalid_encoding(api_client: TestClient) -> None:
    files = {"file": ("report.csv", b"itemCode\n\x81\x00invalid", "text/csv")}
    response = api_client.post("/api/v1/import/affiliate-csv", files=files)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
