from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.importer import import_affiliate_csv
from app.models import Base, ImportErrorRecord, Result
from tests.conftest import make_product, make_result


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


CSV_HEADER = "itemCode,商品URL,集計期間(開始),集計期間(終了),クリック数,成果件数,成果報酬額"


def _to_shift_jis(text: str) -> bytes:
    return text.encode("cp932")


def test_import_affiliate_csv_matches_by_item_code_and_creates_result() -> None:
    session = _make_session()
    product = make_product(session, item_code="shop1:0001")

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop1:0001,,2026-07-01,2026-07-07,120,3,1500",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 1
    assert summary.updated == 0
    assert summary.error_count == 0

    result = session.execute(select(Result).where(Result.product_id == product.id)).scalar_one()
    assert result.clicks == 120
    assert result.conversions == 3
    assert result.revenue == 1500
    assert result.report_date_from == date(2026, 7, 1)
    assert result.report_date_to == date(2026, 7, 7)


def test_import_affiliate_csv_matches_by_url_when_item_code_missing() -> None:
    session = _make_session()
    product = make_product(
        session, item_code="shop2:0002", item_url="https://item.rakuten.co.jp/shop2/0002/"
    )

    csv_text = "\n".join(
        [
            CSV_HEADER,
            ",https://item.rakuten.co.jp/shop2/0002/,2026-07-01,2026-07-07,50,1,300",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 1
    assert summary.error_count == 0
    result = session.execute(select(Result).where(Result.product_id == product.id)).scalar_one()
    assert result.clicks == 50


def test_import_affiliate_csv_overwrites_existing_period() -> None:
    session = _make_session()
    product = make_product(session, item_code="shop1:0001")
    make_result(
        session,
        product,
        report_date_from=date(2026, 7, 1),
        report_date_to=date(2026, 7, 7),
        clicks=1,
        conversions=0,
        revenue=0,
    )

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop1:0001,,2026-07-01,2026-07-07,999,10,50000",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 0
    assert summary.updated == 1
    results = session.execute(select(Result).where(Result.product_id == product.id)).scalars().all()
    assert len(results) == 1
    assert results[0].clicks == 999
    assert results[0].revenue == 50000


def test_import_affiliate_csv_records_unmatched_rows_as_errors() -> None:
    session = _make_session()

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop9:9999,,2026-07-01,2026-07-07,10,1,100",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 0
    assert summary.updated == 0
    assert summary.error_count == 1
    assert "見つかりません" in summary.errors[0].reason

    errors = session.execute(select(ImportErrorRecord)).scalars().all()
    assert len(errors) == 1


def test_import_affiliate_csv_records_malformed_row_as_error_and_continues() -> None:
    session = _make_session()
    product = make_product(session, item_code="shop1:0001")

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop1:0001,,not-a-date,2026-07-07,10,1,100",
            "shop1:0001,,2026-07-08,2026-07-14,20,2,200",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 1
    assert summary.error_count == 1
    result = session.execute(select(Result).where(Result.product_id == product.id)).scalar_one()
    assert result.report_date_from == date(2026, 7, 8)


def test_import_affiliate_csv_decodes_shift_jis_japanese_values() -> None:
    session = _make_session()
    make_product(session, item_code="shop1:0001", name="日本語の商品名テスト")

    csv_text = "\n".join(
        [
            CSV_HEADER,
            "shop1:0001,,2026-07-01,2026-07-07,10,1,100",
        ]
    )

    summary = import_affiliate_csv(session, _to_shift_jis(csv_text))

    assert summary.imported == 1
    assert summary.error_count == 0
