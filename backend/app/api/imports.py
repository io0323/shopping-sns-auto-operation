from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.importer import import_affiliate_csv
from app.core.db import get_db
from app.schemas.affiliate_import import ImportSummary

router = APIRouter()


@router.post("/import/affiliate-csv")
async def import_affiliate_csv_endpoint(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> ImportSummary:
    raw = await file.read()
    try:
        return import_affiliate_csv(session, raw)
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="文字コードが不正です(Shift-JIS想定)"
        ) from exc
