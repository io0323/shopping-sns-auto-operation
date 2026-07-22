import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.operation_log import record_operation
from app.models import Base, OperationLog


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_record_operation_does_not_commit_by_itself() -> None:
    session = _make_session()
    target_id = uuid.uuid4()

    record_operation(session, operation="approve", target_type="content", target_id=target_id)
    session.rollback()

    assert session.execute(select(OperationLog)).scalars().all() == []


def test_record_operation_persists_after_caller_commits() -> None:
    session = _make_session()
    target_id = uuid.uuid4()

    record_operation(session, operation="approve", target_type="content", target_id=target_id)
    session.commit()

    logs = session.execute(select(OperationLog)).scalars().all()
    assert len(logs) == 1
    assert logs[0].operation == "approve"
    assert logs[0].target_id == target_id
