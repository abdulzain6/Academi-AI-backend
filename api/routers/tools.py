import io
import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from api.auth import verify_cronjob_request
from ..globals import (
    redis_cache_manager,
)
import logging
from io import BytesIO


router = APIRouter()

MEDIA_TYPE_MAPPING_IMG = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff"
}
MEDIA_TYPE_MAPPING = {".mp4": "video/mp4"}
MAX_FILE_SIZE_MB = 500  # Maximum file size allowed (in MB)


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
    print(extension)
    if extension.lower() not in MEDIA_TYPE_MAPPING_IMG:
        raise HTTPException(status_code=415, detail="Unsupported media type")

    media_type = MEDIA_TYPE_MAPPING_IMG[extension.lower()]
    im_io = BytesIO(im_bytes)
    logging.info(f"Getting redis doc for {doc_id}")

    return StreamingResponse(
        io.BytesIO(im_io.getvalue()),
        headers={"Content-Disposition": "inline"},
        media_type=media_type
    )
    

@router.get("/retrieve_video/{video_id}")
def retrieve_video(video_id: str):
    video_data = redis_cache_manager.get(video_id)
    if video_data is None:
        raise HTTPException(status_code=404, detail="Video not found/ Link expired")

    return StreamingResponse(
        iter([video_data]),  # Stream the video data
        media_type=MEDIA_TYPE_MAPPING[".mp4"]
    )

@router.post("/upload_video/")
def upload_video(file: UploadFile = File(...), _ = Depends(verify_cronjob_request)):
    extension = os.path.splitext(file.filename)[-1].lower()
    
    if extension not in MEDIA_TYPE_MAPPING:
        raise HTTPException(status_code=415, detail="Unsupported video format")

    # Check the file size
    file.file.seek(0, os.SEEK_END)  # Move pointer to end to get size
    file_size = file.file.tell()  # Get size in bytes
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max size is 500MB.")
    file.file.seek(0)  # Reset file pointer to start after size check

    # Read file content
    video_bytes = file.file.read()

    # Generate a unique ID for the video
    video_id = str(uuid.uuid4()) + extension

    # Store video in Redis with a TTL (optional, e.g., 1 hour)
    redis_cache_manager.setex(video_id, 3600, video_bytes)  # 3600 seconds = 1 hour

    # Return the video ID
    return {"video_id": video_id}