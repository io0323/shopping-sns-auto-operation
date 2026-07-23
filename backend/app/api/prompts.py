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
    # agent単位で行ロックし、同時activateによる複数is_active=true化を防ぐ
    # (SQLiteではwith_for_updateは無視されるが、PostgreSQL移行後は有効に働く)
    stmt = select(PromptVersion).where(PromptVersion.agent == agent).with_for_update()
    agent_versions = {row.id: row for row in session.execute(stmt).scalars()}

    target = agent_versions.get(payload.prompt_version_id)
    if target is None:
        raise HTTPException(status_code=404, detail="プロンプトが見つかりません")

    for other in agent_versions.values():
        if other.id != target.id and other.is_active:
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
