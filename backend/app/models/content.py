import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Content(TimestampMixin, Base):
    __tablename__ = "contents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidates.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    x_post: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str] = mapped_column(Text, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_breakdown: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    eval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    regen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_by_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
