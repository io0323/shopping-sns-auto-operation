import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    genre_id: Mapped[str] = mapped_column(String(32), nullable=False)
    genre_name: Mapped[str] = mapped_column(String(128), nullable=False)
    shop_code: Mapped[str] = mapped_column(String(128), nullable=False)
    shop_name: Mapped[str] = mapped_column(String(256), nullable=False)
    item_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    metrics: Mapped[list["ProductMetric"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductMetric(Base):
    __tablename__ = "product_metrics"
    __table_args__ = (
        UniqueConstraint("product_id", "snapshot_date", name="uq_product_metrics_product_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    point_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_average: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_genre_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    product: Mapped[Product] = relationship(back_populates="metrics")
