from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.export import build_export_queue
from app.core.db import get_db
from app.schemas.export import ExportQueueResponse

router = APIRouter()


@router.get("/export/queue")
def get_export_queue(session: Session = Depends(get_db)) -> ExportQueueResponse:
    return ExportQueueResponse(items=build_export_queue(session))
