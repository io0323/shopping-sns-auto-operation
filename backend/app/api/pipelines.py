from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.harness.job_queue import PipelineAlreadyRunningError
from app.harness.pipeline import run_daily_pipeline

router = APIRouter()


@router.post("/pipelines/daily/run")
def trigger_daily_pipeline(session: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return run_daily_pipeline(session)
    except PipelineAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
