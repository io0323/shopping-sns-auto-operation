import csv
import io
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportErrorRecord, Product, Result
from app.schemas.affiliate_import import ImportErrorOut, ImportSummary

REQUIRED_COLUMNS = (
    "集計期間(開始)",
    "集計期間(終了)",
    "クリック数",
    "成果件数",
    "成果報酬額",
)


def decode_shift_jis(raw: bytes) -> str:
    return raw.decode("cp932")


def _resolve_product(session: Session, row: dict[str, str]) -> Product | None:
    item_code = (row.get("itemCode") or "").strip()
    if item_code:
        product = session.execute(
            select(Product).where(Product.item_code == item_code)
        ).scalar_one_or_none()
        if product is not None:
            return product

    item_url = (row.get("商品URL") or "").strip()
    if item_url:
        return session.execute(
            select(Product).where(Product.item_url == item_url)
        ).scalar_one_or_none()
    return None


def _parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _parse_int(value: str) -> int:
    return int(value.strip().replace(",", ""))


def _raw_line(row: dict[str, str]) -> str:
    return ",".join(f"{key}={value}" for key, value in row.items())


def import_affiliate_csv(session: Session, raw: bytes) -> ImportSummary:
    text = decode_shift_jis(raw)
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    updated = 0
    errors: list[ImportErrorOut] = []

    for row in reader:
        try:
            product = _resolve_product(session, row)
            if product is None:
                raise ValueError("itemCode/商品URLに一致する商品が見つかりません")

            report_date_from = _parse_date(row["集計期間(開始)"])
            report_date_to = _parse_date(row["集計期間(終了)"])
            clicks = _parse_int(row["クリック数"])
            conversions = _parse_int(row["成果件数"])
            revenue = _parse_int(row["成果報酬額"])
        except (KeyError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else f"必須カラムがありません: {exc}"
            errors.append(ImportErrorOut(raw_line=_raw_line(row), reason=reason))
            session.add(ImportErrorRecord(raw_line=_raw_line(row), reason=reason))
            continue

        existing = session.execute(
            select(Result).where(
                Result.product_id == product.id,
                Result.report_date_from == report_date_from,
                Result.report_date_to == report_date_to,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.clicks = clicks
            existing.conversions = conversions
            existing.revenue = revenue
            session.add(existing)
            updated += 1
        else:
            session.add(
                Result(
                    product_id=product.id,
                    report_date_from=report_date_from,
                    report_date_to=report_date_to,
                    clicks=clicks,
                    conversions=conversions,
                    revenue=revenue,
                )
            )
            imported += 1

    session.commit()
    return ImportSummary(imported=imported, updated=updated, error_count=len(errors), errors=errors)
