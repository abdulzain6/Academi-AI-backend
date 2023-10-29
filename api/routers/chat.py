import logging
import queue
import threading
from typing import Generator, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    collection_manager,
    chat_manager,
    file_manager,
    conversation_manager,
)
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks
from ..dependencies import can_use_premium_model, require_points_for_feature
from pydantic import BaseModel


router = APIRouter()


class ChatCollectionInput(BaseModel):
    collection_name: str
    chat_history: Optional[list[tuple[str, str]]] = None
    prompt: str
    language: str = "English"


class ChatFileInput(ChatCollectionInput):
    file_name: str


def convert_message_pairs_to_tuples(
    message_pairs: list[MessagePair],
) -> list[tuple[str, str]]:
    return [(pair.human_message, pair.bot_response) for pair in message_pairs]



@router.post("/chat-collection-stream")
@require_points_for_feature("CHAT")
def chat_collection_stream(
    data: ChatCollectionInput,
    conversation_id: Optional[str] = None,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity)
):
    logging.info(f"Initiating chat_collection_stream, user {user_id}")
    if conversation_id and not conversation_manager.conversation_exists(
        user_id, conversation_id
    ):
        raise HTTPException(
            detail="Conversation not found", status_code=status.HTTP_400_BAD_REQUEST
        )

    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            data.collection_name, user_id
        )
    ):
        raise HTTPException(
            detail="Collection not found", status_code=status.HTTP_400_BAD_REQUEST
        )
    if collection.number_of_files == 0:
        raise HTTPException(
            detail="Collection has no files", status_code=status.HTTP_400_BAD_REQUEST
        )

    chat_history = (
        convert_message_pairs_to_tuples(
            conversation_manager.get_messages(user_id, conversation_id)
        )
        if conversation_id
        else data.chat_history
    ) or []
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    logging.info(f"Using model {model_name} to chat collection for user {user_id}")

    data_queue = queue.Queue()

    def callback(data: str) -> None:
        data_queue.put(data)

    def data_generator() -> Generator[str, None, None]:
        yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, data.prompt, response.generations[0][0].text
            )

    def run_chat() -> None:
        try:
            chat_manager.chat(
                collection.vectordb_collection_name,
                data.prompt,
                chat_history,
                data.language,
                True,
                model_name=model_name,
                callback_func=callback,
                on_end_callback=on_end_callback,
            )
        except Exception as e:
            logging.error(f"Error running chat in chat_collection_stream: {e}")
            error_message = "Error in getting response"
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback(None)

    threading.Thread(target=run_chat).start()

    return StreamingResponse(data_generator())


@router.post("/chat-file-stream")
@require_points_for_feature("CHAT")
def chat_file_stream(
    data: ChatFileInput,
    conversation_id: Optional[str] = None,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity)
):
    logging.info("Initiating chat_file_stream")
    if conversation_id and not conversation_manager.conversation_exists(
        user_id, conversation_id
    ):
        raise HTTPException(
            detail="Conversation not found", status_code=status.HTTP_400_BAD_REQUEST
        )

    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            data.collection_name, user_id
        )
    ):
        raise HTTPException(
            detail="Collection not found", status_code=status.HTTP_400_BAD_REQUEST
        )
    if collection.number_of_files == 0:
        raise HTTPException(
            detail="Collection has no files", status_code=status.HTTP_400_BAD_REQUEST
        )

    if not file_manager.file_exists(
        collection_uid=collection.collection_uid,
        user_id=user_id,
        filename=data.file_name,
    ):
        raise HTTPException(
            detail="File not found.", status_code=status.HTTP_400_BAD_REQUEST
        )

    chat_history = (
        convert_message_pairs_to_tuples(
            conversation_manager.get_messages(user_id, conversation_id)
        )
        if conversation_id
        else data.chat_history
    ) or []
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    logging.info(f"Using model {model_name} to chat collection for user {user_id}")
    data_queue = queue.Queue()

    def callback(data: str) -> None:
        data_queue.put(data)

    def data_generator() -> Generator[str, None, None]:
        yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, data.prompt, response.generations[0][0].text
            )

    def run_chat() -> None:
        try:
            chat_manager.chat(
                collection.vectordb_collection_name,
                data.prompt,
                chat_history,
                data.language,
                True,
                model_name=model_name,
                callback_func=callback,
                filename=data.file_name,
                on_end_callback=on_end_callback,
            )
        except Exception as e:
            logging.error(f"Error running chat in chat_file_stream: {e}")
            error_message = "Error in getting response"
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback(None)

    threading.Thread(target=run_chat).start()

    return StreamingResponse(data_generator())

