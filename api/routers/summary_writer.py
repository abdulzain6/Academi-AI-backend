import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.lib.summary_writer import SummaryWriter
from ..auth import get_user_id, verify_play_integrity
from ..globals import collection_manager, file_manager 
from ..dependencies import get_model, require_points_for_feature, can_use_premium_model
from .utils import select_random_chunks

router = APIRouter()


class SummaryInput(BaseModel):
    data: Optional[str] = None
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    word_count: int
    instructions: str



@router.post("/write-summary")
@require_points_for_feature("SUMMARY")
def write_summary(
    input: SummaryInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if not input.data and not input.collection_name:
        raise HTTPException(400, detail="Data or collection name must be provided")

    if input.collection_name and not collection_manager.collection_exists(
        input.collection_name, user_id
    ):
        raise HTTPException(400, detail="Collection not found!")

    if input.file_name and not file_manager.file_exists(
        collection_uid=collection_manager.resolve_collection_uid(input.collection_name, user_id=user_id),
        user_id=user_id,
        filename=input.file_name,
    ):
        raise HTTPException(400, detail="File not found!")

    if input.data:
        data = input.data
    elif input.file_name:
        file = file_manager.get_file_by_name(
            user_id=user_id,
            collection_name=input.collection_name,
            filename=input.file_name,
        )
        data = file.file_content
    else:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=input.collection_name
        )
        data = "\n".join([file.file_content for file in files])
        
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    model = get_model({"temperature": 0.3}, False, premium_model)
    summary_writer = SummaryWriter(model)
    content = summary_writer.get_content(
        select_random_chunks(data, 600, 1500), input.word_count, input.instructions
    )

    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)
