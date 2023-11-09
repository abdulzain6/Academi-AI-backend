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
    chat_manager_agent_non_retrieval
)
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks
from ..dependencies import can_use_premium_model, require_points_for_feature, get_model_and_fallback
from pydantic import BaseModel
from openai.error import OpenAIError

router = APIRouter()


class ChatGeneralInput(BaseModel):
    chat_history: Optional[list[tuple[str, str]]] = None
    prompt: str
    language: str = "English"

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
    model_default, model_fallback  = get_model_and_fallback({"temperature": 0.3}, True, premium_model)
    data_queue = queue.Queue()
    
    def data_generator() -> Generator[str, None, None]:
       # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    #yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, data.prompt, response
            )

    def run_chat() -> None:
        try:
            chat_manager.run_agent(
                collection_name=collection.vectordb_collection_name,
                prompt=data.prompt,
                chat_history=chat_history,
                language=data.language,
                llm=model_default,
                callback=callback,
                on_end_callback=on_end_callback,
            )
        except OpenAIError:
            try:
                chat_manager.chat(
                    collection_name=collection.vectordb_collection_name,
                    prompt=data.prompt,
                    chat_history=chat_history,
                    language=data.language,
                    llm=model_fallback,
                    callback_func=callback,
                    on_end_callback=on_end_callback,
                )
            except Exception as e:
                logging.error(f"Error running chat in chat_collection_stream: {e}")
                error_message = "Error in getting response"
                for chunk in split_into_chunks(error_message, 4):
                    callback(chunk)
                callback(None)
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
    model_default, model_fallback  = get_model_and_fallback({"temperature": 0.3}, True, premium_model)

    data_queue = queue.Queue()

    def data_generator() -> Generator[str, None, None]:
       # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    #yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, data.prompt, response
            )

    def run_chat() -> None:
        try:
            chat_manager.run_agent(
                collection_name=collection.vectordb_collection_name,
                prompt=data.prompt,
                chat_history=chat_history,
                language=data.language,
                llm=model_default,
                callback=callback,
                on_end_callback=on_end_callback,
                filename=data.file_name,
            )
        except OpenAIError:
            try:
                chat_manager.chat(
                    collection_name=collection.vectordb_collection_name,
                    prompt=data.prompt,
                    chat_history=chat_history,
                    language=data.language,
                    llm=model_fallback,
                    callback_func=callback,
                    on_end_callback=on_end_callback,
                    filename=data.file_name,
                )
            except Exception as e:
                logging.error(f"Error running chat in chat_file_stream: {e}")
                error_message = "Error in getting response"
                for chunk in split_into_chunks(error_message, 4):
                    callback(chunk)
                callback(None)
        except Exception as e:
            logging.error(f"Error running chat in chat_file_stream: {e}")
            error_message = "Error in getting response"
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback(None)

    threading.Thread(target=run_chat).start()

    return StreamingResponse(data_generator())


@router.post("/general-chat")
@require_points_for_feature("CHAT")
def chat_general_stream(
    data: ChatGeneralInput,
    conversation_id: Optional[str] = None,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity)
):
    logging.info("Initiating chat agents")
    
    if conversation_id and not conversation_manager.conversation_exists(
        user_id, conversation_id
    ):
        raise HTTPException(
            detail="Conversation not found", status_code=status.HTTP_400_BAD_REQUEST
        )

    chat_history = (
        convert_message_pairs_to_tuples(
            conversation_manager.get_messages(user_id, conversation_id)
        )
        if conversation_id
        else data.chat_history
    ) or []
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)        
    model_default, model_fallback  = get_model_and_fallback({"temperature": 0.3}, True, premium_model)

    data_queue = queue.Queue()

    def data_generator() -> Generator[str, None, None]:
       # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    #yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, data.prompt, response
            )

    def run_chat() -> None:
        try:
            chat_manager_agent_non_retrieval.run_agent(
                prompt=data.prompt,
                chat_history=chat_history,
                language=data.language,
                llm=model_default,
                callback=callback,
                on_end_callback=on_end_callback,
            )
        except OpenAIError:
            try:
                chat_manager_agent_non_retrieval.chat(
                    prompt=data.prompt,
                    chat_history=chat_history,
                    language=data.language,
                    llm=model_fallback,
                    callback_func=callback,
                    on_end_callback=on_end_callback,
                )
            except Exception as e:
                logging.error(f"Error running chat in general chat: {e}")
                error_message = "Error in getting response"
                for chunk in split_into_chunks(error_message, 4):
                    callback(chunk)
                callback(None)
        except Exception as e:
            logging.error(f"Error running chat in general chat: {e}")
            error_message = "Error in getting response"
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback(None)

    threading.Thread(target=run_chat).start()

    return StreamingResponse(data_generator())
