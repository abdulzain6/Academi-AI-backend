from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from ..auth import get_current_user, get_user_id, verify_play_integrity
from ..globals import (
    redis_cache_manager,
)
import logging
from io import BytesIO
from fastapi.responses import StreamingResponse


router = APIRouter()


@router.get("/document/{doc_id}")
def get_document(doc_id: str):
    doc_bytes = redis_cache_manager.get(doc_id)

    if doc_bytes is None:
        raise HTTPException(status_code=404, detail="Document not found/ Link expired")

    pdf_io = BytesIO(doc_bytes)
    logging.info(f"Getting redis doc for {doc_id}")
    headers = {
        'Content-Disposition': f'attachment; filename={doc_id}.pdf'
    }
    return Response(content=pdf_io.read(), media_type="application/pdf", headers=headers)