from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.export import build_export_queue
from app.models import Base
from tests.conftest import make_candidate, make_content, make_product


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_build_export_queue_only_includes_approved_ordered_by_scheduled_at() -> None:
    session = _make_session()
    product = make_product(session)
    candidate = make_candidate(session, product)
    make_content(session, product, candidate, status="evaluated")
    later = make_content(
        session,
        product,
        candidate,
        status="approved",
        scheduled_at=datetime(2026, 7, 25, 9, 0),
    )
    unscheduled = make_content(session, product, candidate, status="approved", scheduled_at=None)
    earlier = make_content(
        session,
        product,
        candidate,
        status="approved",
        scheduled_at=datetime(2026, 7, 23, 9, 0),
    )

    items = build_export_queue(session)

    assert [item.content_id for item in items] == [earlier.id, later.id, unscheduled.id]


def test_build_export_queue_formats_room_text_and_flags_ad_disclosure() -> None:
    session = _make_session()
    product = make_product(session)
    candidate = make_candidate(session, product)
    make_content(
        session,
        product,
        candidate,
        status="approved",
        title="タイトル",
        description="説明文",
        hashtags=["#a", "#b"],
        x_post="投稿テキスト #ad",
    )

    items = build_export_queue(session)

    assert len(items) == 1
    item = items[0]
    assert item.room_text == "タイトル\n\n説明文\n\n#a #b"
    assert item.x_text == "投稿テキスト #ad"
    assert item.has_ad_disclosure is True
    assert len(item.checklist) > 0


def test_build_export_queue_flags_missing_ad_disclosure() -> None:
    session = _make_session()
    product = make_product(session)
    candidate = make_candidate(session, product)
    make_content(session, product, candidate, status="approved", x_post="広告表記なし投稿")

    items = build_export_queue(session)

    assert items[0].has_ad_disclosure is False
