from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id
from ..globals import conversation_manager as message_manager
from ..globals import collection_manager
from ..lib.models import UserLatestConversations, MessagePair
from ..lib.models import ConversationMetadata
from pydantic import BaseModel
from ..auth import get_user_id, verify_play_integrity
from typing import List
import logging


class DeleteConversationResponse(BaseModel):
    deleted_rows: int


class AddConversationResponse(BaseModel):
    conversation_id: str


class AddMessageRequest(BaseModel):
    conversation_id: str
    human_message: str
    bot_response: str


router = APIRouter()


@router.post("/add_conversation", response_model=AddConversationResponse)
def add_conversation(
    metadata: ConversationMetadata,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Adding convo {user_id}")
    if metadata.collection_name and not collection_manager.collection_exists(
        metadata.collection_name, user_id
    ):
        raise HTTPException(400, detail="Collection does not exist")
    conversation_id = message_manager.add_conversation(user_id, metadata)
    return AddConversationResponse(conversation_id=conversation_id)


@router.post("/add_message")
def add_message(
    request: AddMessageRequest,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        logging.info(f"Adding message {user_id}")
        if not message_manager.conversation_exists(user_id, request.conversation_id):
            logging.error(f"Conversation doesnt exist {user_id}")
            raise HTTPException(400, detail="Conversation does not exist")

        message_manager.add_message(
            user_id,
            request.conversation_id,
            request.human_message,
            request.bot_response,
        )
        return {"message": "Added Message Successfully!"}
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/get_messages", response_model=List[MessagePair])
def get_messages(
    conversation_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Getting messages {user_id}")
    if not message_manager.conversation_exists(user_id, conversation_id):
        logging.error(f"Coversation not found {user_id}")
        raise HTTPException(400, detail="Conversation does not exist")
    messages = message_manager.get_messages(user_id, conversation_id)
    return [] if messages is None else messages


@router.get("/get_all_conversations")
def get_all_conversations(
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Getting all convo {user_id}")
    conversations = message_manager.get_all_conversations(user_id)
    if conversations is None:
        return UserLatestConversations(user_id=user_id, conversations=[])
    return UserLatestConversations(user_id=user_id, conversations=conversations)


@router.delete("/delete_conversation", response_model=DeleteConversationResponse)
def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Deleting convo {user_id}")
    if not message_manager.conversation_exists(user_id, conversation_id):
        logging.error(f"Coversation not found {user_id}")
        raise HTTPException(400, detail="Conversation does not exist")
    try:
        deleted_count = message_manager.delete_conversation(user_id, conversation_id)
        return DeleteConversationResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting conversation, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error deleting conversation, {e}"
        ) from e


@router.delete("/delete_all_conversations", response_model=DeleteConversationResponse)
def delete_all_conversations(
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Deleting all convo {user_id}")
    try:
        deleted_count = message_manager.delete_all_conversations(user_id)
        return DeleteConversationResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting all conversations, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error deleting all conversations, {e}"
        ) from e
