import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.lib.summary_writer import SummaryWriter
from ..auth import get_user_id, verify_play_integrity
from ..globals import collection_manager, file_manager, global_chat_model_kwargs, global_chat_model
from ..dependencies import require_points_for_feature, can_use_premium_model
from random import sample

router = APIRouter()


class SummaryInput(BaseModel):
    data: Optional[str] = None
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    word_count: int
    instructions: str


def select_random_chunks(text: str, chunk_size: int, total_length: int) -> str:
    if len(text) <= chunk_size:
        return text

    # Split the text into chunks
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    # Calculate the number of chunks needed to meet the 'total_length'
    num_chunks_needed = min(len(chunks), total_length // chunk_size)

    # Pick random unique chunks
    selected_indices = sample(range(len(chunks)), num_chunks_needed)
    selected_indices.sort()  # Sort the indices to maintain original order

    # Concatenate the selected chunks to form the output string
    selected_chunks = [chunks[i] for i in selected_indices]
    return ''.join(selected_chunks)[:total_length]


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
    kwargs = {**global_chat_model_kwargs}
    if model_name:
        kwargs["model"] = model_name
    
    summary_writer = SummaryWriter(
        global_chat_model,
        llm_kwargs={
            "temperature": 0.3,
            **kwargs
        }
    )
    content = summary_writer.get_content(
        select_random_chunks(data, 1000, 5000), input.word_count, input.instructions
    )

    content["pdf"] = base64.b64encode(content["pdf"]).decode()
    content["docx"] = base64.b64encode(content["docx"]).decode()
    return JSONResponse(content=content)
