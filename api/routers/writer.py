import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..auth import get_current_user, get_user_id
from ..globals import user_manager, knowledge_manager, collection_manager, writer
from ..lib.writer import ContentInput

router = APIRouter()

@router.get("/write")
def write_content(input: ContentInput, user_id = Depends(get_user_id)):
    content = writer.get_content(input)    
    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)