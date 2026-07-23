from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.operation_log import record_operation
from app.models import PromptVersion
from app.schemas.prompt import PromptActivateRequest, PromptVersionOut

router = APIRouter()


@router.post("/prompts/{agent}/activate")
def activate_prompt(
    agent: str, payload: PromptActivateRequest, session: Session = Depends(get_db)
) -> PromptVersionOut:
    target = session.get(PromptVersion, payload.prompt_version_id)
    if target is None or target.agent != agent:
        raise HTTPException(status_code=404, detail="プロンプトが見つかりません")

    stmt = select(PromptVersion).where(
        PromptVersion.agent == agent, PromptVersion.is_active.is_(True)
    )
    for other in session.execute(stmt).scalars():
        other.is_active = False
        session.add(other)

    target.is_active = True
    session.add(target)
    record_operation(
        session,
        operation="activate_prompt",
        target_type="prompt_version",
        target_id=target.id,
        detail={"agent": agent, "version": target.version},
    )
    session.commit()

    return PromptVersionOut.model_validate(target)
