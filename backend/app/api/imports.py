from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.importer import import_affiliate_csv
from app.core.db import get_db
from app.schemas.affiliate_import import ImportSummary

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/import/affiliate-csv")
async def import_affiliate_csv_endpoint(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> ImportSummary:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="アップロードファイルが大きすぎます(上限10MB)"
        )
    try:
        return import_affiliate_csv(session, raw)
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="文字コードが不正です(Shift-JIS想定)"
        ) from exc
