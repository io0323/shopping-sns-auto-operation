import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.llm import LlmClient
from app.core.db import get_db, get_session_factory
from app.harness.generation import generate_and_evaluate_candidates
from app.models import Candidate, Job
from app.schemas.content import GenerateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_generate_job(job_id: uuid.UUID, candidate_ids: list[uuid.UUID]) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        job = session.get(Job, job_id)
        if job is None:
            return

        job.status = "running"
        session.commit()

        try:
            stmt = select(Candidate).where(Candidate.id.in_(candidate_ids))
            candidates = list(session.execute(stmt).scalars().all())
            llm_client = LlmClient(session)
            result = generate_and_evaluate_candidates(session, llm_client, job.id, candidates)
            job.status = "done"
            payload = dict(job.payload or {})
            payload["result"] = result
            job.payload = payload
        except Exception as exc:
            logger.exception("generation job failed: job_id=%s", job_id)
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = datetime.now(UTC)
            session.commit()


@router.post("/generate", status_code=202)
def trigger_generate(
    payload: GenerateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    if not payload.candidate_ids:
        raise HTTPException(status_code=422, detail="candidate_idsを1件以上指定してください")

    stmt = select(Candidate.id).where(Candidate.id.in_(payload.candidate_ids))
    found_ids = {row[0] for row in session.execute(stmt).all()}
    missing = set(payload.candidate_ids) - found_ids
    if missing:
        missing_str = ", ".join(str(cid) for cid in missing)
        raise HTTPException(
            status_code=422, detail=f"存在しないcandidate_idが含まれています: {missing_str}"
        )

    job = Job(
        pipeline="manual_generate",
        step="generate",
        status="pending",
        payload={"candidate_ids": [str(cid) for cid in payload.candidate_ids]},
        started_at=datetime.now(UTC),
    )
    session.add(job)
    session.commit()

    background_tasks.add_task(_run_generate_job, job.id, payload.candidate_ids)
    return {"job_id": str(job.id)}
