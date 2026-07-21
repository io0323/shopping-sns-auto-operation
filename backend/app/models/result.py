import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "report_date_from", "report_date_to", name="uq_results_product_period"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    content_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contents.id"), nullable=True
    )
    report_date_from: Mapped[date] = mapped_column(Date, nullable=False)
    report_date_to: Mapped[date] = mapped_column(Date, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="csv_import")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
