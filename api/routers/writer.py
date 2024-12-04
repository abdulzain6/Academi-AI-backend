import base64
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from ..auth import get_user_id, verify_play_integrity
from ..lib.writer import ContentInput, Writer
from ..dependencies import require_points_for_feature, can_use_premium_model, get_model

router = APIRouter()

@router.post("/write")
@require_points_for_feature("WRITER")
def write_content(
    input: ContentInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):     
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    model = get_model({"temperature": 0.3}, False, premium_model, alt=False)
    writer = Writer(model)
    logging.info(f"Writer request from {user_id}, Data: {input}")
    content = writer.get_content(input)
    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)
