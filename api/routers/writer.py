import base64
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from ..auth import get_user_id
from ..globals import writer
from ..lib.writer import ContentInput

router = APIRouter()

@router.post("/write")
def write_content(input: ContentInput, user_id = Depends(get_user_id)):
    content = writer.get_content(input)    
    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)