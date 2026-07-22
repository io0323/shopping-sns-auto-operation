import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import OperationLog


def record_operation(
    session: Session,
    operation: str,
    target_type: str,
    target_id: uuid.UUID,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        OperationLog(
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )
    session.commit()
