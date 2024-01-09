import io
import os
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from ..globals import (
    redis_cache_manager,
)
import logging
from io import BytesIO


router = APIRouter()

MEDIA_TYPE_MAPPING = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff"
}

@router.get("/document/{doc_id}")
def get_document(doc_id: str):
    doc_bytes = redis_cache_manager.get(doc_id)

    if doc_bytes is None:
        raise HTTPException(status_code=404, detail="Document not found/ Link expired")

    root, extension = os.path.splitext(doc_id)
    pdf_io = BytesIO(doc_bytes)
    logging.info(f"Getting redis doc for {doc_id}")
    headers = {
        'Content-Disposition': f'attachment; filename={doc_id}{extension}'
    }
    return Response(content=pdf_io.read(), headers=headers)


@router.get("/image/{doc_id}")
def get_image(doc_id: str):
    im_bytes = redis_cache_manager.get(doc_id)

    if im_bytes is None:
        raise HTTPException(status_code=404, detail="Image not found/ Link expired")

    root, extension = os.path.splitext(doc_id)
    if extension.lower() not in MEDIA_TYPE_MAPPING:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    media_type = MEDIA_TYPE_MAPPING[extension.lower()]
    im_io = BytesIO(im_bytes)
    logging.info(f"Getting redis doc for {doc_id}")

    return StreamingResponse(
        io.BytesIO(im_io.getvalue()),
        headers={"Content-Disposition": "inline"},
        media_type=media_type
    )