from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_current_user
from ..globals import collection_manager, chat_manager, file_manager
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()


class ChatCollectionInput(BaseModel):
    collection_name: str
    chat_history: list[tuple[str, str]]
    prompt: str
    model: str = "gpt-3.5-turbo"
    language: str = "English"
    
class ChatFileInput(ChatCollectionInput):
    file_name: str


@router.post("/chat-collection")
async def chat_collection(
    data: ChatCollectionInput, current_user=Depends(get_current_user)
):
    if collection := collection_manager.get_collection_by_name_and_user(
        data.collection_name, current_user["user_id"]
    ):
        if collection.number_of_files == 0:
            raise HTTPException(
                detail="Collection has no files", status_code=status.HTTP_404_NOT_FOUND
            )
        return chat_manager.chat(
            collection.vectordb_collection_name,
            data.prompt,
            data.chat_history,
            data.language,
            False,
            model_name=data.model,
        )
    else:
        raise HTTPException(
            detail="Collection not found", status_code=status.HTTP_404_NOT_FOUND
        )

@router.post("/chat-file")
async def chat_file(
    data: ChatFileInput, current_user=Depends(get_current_user)
):
    if collection := collection_manager.get_collection_by_name_and_user(
        data.collection_name, current_user["user_id"]
    ):
        if collection.number_of_files == 0:
            raise HTTPException(
                detail="Collection has no files", status_code=status.HTTP_404_NOT_FOUND
            )
        if not file_manager.file_exists(data.collection_name, current_user["user_id"], data.file_name):
            raise HTTPException(
                detail="File not found.", status_code=status.HTTP_404_NOT_FOUND
            )
            
        return chat_manager.chat(
            collection.vectordb_collection_name,
            data.prompt,
            data.chat_history,
            data.language,
            False,
            model_name=data.model,
            filename=data.file_name
        )
    else:
        raise HTTPException(
            detail="Collection not found", status_code=status.HTTP_404_NOT_FOUND
        )