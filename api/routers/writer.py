import base64
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from ..auth import get_user_id, verify_play_integrity
from ..globals import writer
from ..lib.writer import ContentInput
from ..decorators import openai_token_tracking_decorator, require_points_for_feature

router = APIRouter()

@openai_token_tracking_decorator
@router.post("/write")
def write_content(
    input: ContentInput,
    user_id=Depends(get_user_id),
    _=Depends(require_points_for_feature("WRITER")),
    play_integrity_verified=Depends(verify_play_integrity)
):
    content = writer.get_content(input)
    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)
