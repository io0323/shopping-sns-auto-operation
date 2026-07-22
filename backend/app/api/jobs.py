import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Job
from app.schemas.job import JobOut

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, session: Session = Depends(get_db)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return JobOut.model_validate(job)
