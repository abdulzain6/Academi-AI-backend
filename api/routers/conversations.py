from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id
from ..globals import conversation_manager as message_manager
from ..lib.database import UserLatestConversations, MessagePair
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import logging

class DeleteConversationResponse(BaseModel):
    deleted_rows: int

class AddConversationResponse(BaseModel):
    conversation_id: str

class AddMessageRequest(BaseModel):
    conversation_id: str
    human_message: str
    bot_response: str
    

class AddConversationRequest(BaseModel):
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    timestamp: Optional[datetime] = None

router = APIRouter()
    

@router.post("/add_conversation", response_model=AddConversationResponse)
def add_conversation(metadata: AddConversationRequest, user_id: str = Depends(get_user_id)):
    try:
        conversation_id = message_manager.add_conversation(user_id, metadata.model_dump())
        return AddConversationResponse(conversation_id=conversation_id)
    except Exception as e:
        logging.error(f"Error adding conversation, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error adding conversation, {e}") from e

@router.post("/add_message")
def add_message(request: AddMessageRequest, user_id: str = Depends(get_user_id)):
    try:
        message_manager.add_message(user_id, request.conversation_id, request.human_message, request.bot_response)
        return {"message" : "Added Message Successfully!"}
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except Exception as e:
        logging.error(f"Error adding message, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error adding message, {e}") from e

@router.get("/get_messages", response_model=List[MessagePair])
def get_messages(conversation_id: str, user_id: str = Depends(get_user_id)):
    messages = message_manager.get_messages(user_id, conversation_id)
    return [] if messages is None else messages

@router.get("/get_all_conversations")
def get_all_conversations(user_id: str = Depends(get_user_id)):
    conversations = message_manager.get_all_conversations(user_id)
    if conversations is None:
        conversations = UserLatestConversations(user_id=user_id, conversations=[])
    return UserLatestConversations(user_id=user_id, conversations=conversations)

@router.delete("/delete_conversation", response_model=DeleteConversationResponse)
def delete_conversation(conversation_id: str, user_id: str = Depends(get_user_id)):
    try:
        deleted_count = message_manager.delete_conversation(user_id, conversation_id)
        return DeleteConversationResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting conversation, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error deleting conversation, {e}") from e

@router.delete("/delete_all_conversations", response_model=DeleteConversationResponse)
def delete_all_conversations(user_id: str = Depends(get_user_id)):
    try:
        deleted_count = message_manager.delete_all_conversations(user_id)
        return DeleteConversationResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting all conversations, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error deleting all conversations, {e}") from e