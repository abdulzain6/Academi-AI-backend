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
    chat_manager_agent_non_retrieval,
    knowledge_manager,
)
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks
from ..dependencies import (
    can_use_premium_model,
    require_points_for_feature,
    get_model_and_fallback,
)
from pydantic import BaseModel
from openai import OpenAIError
from langchain.tools import StructuredTool, Tool
from .utils import select_random_chunks, find_most_similar
from langchain.pydantic_v1 import BaseModel as OldBaseModel
from langchain.pydantic_v1 import Field as OldField

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
    play_integrity_verified=Depends(verify_play_integrity),
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
    model_default, model_fallback = get_model_and_fallback(
        {"temperature": 0.3}, True, premium_model, alt=True
    )
    data_queue = queue.Queue()

    def data_generator() -> Generator[str, None, None]:
        # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    # yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            try:
                conversation_manager.add_message(
                    user_id, conversation_id, data.prompt, response
                )
            except Exception as e:
                logging.error(f"Error adding message {e}")
            logging.info(f"Added ({data.prompt}, {response}) {conversation_id}")

    def run_chat() -> None:
        try:
            chat_manager.chat(
                collection_name=collection.vectordb_collection_name,
                prompt=data.prompt,
                chat_history=chat_history,
                language=data.language,
                llm=model_default,
                callback_func=callback,
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
    play_integrity_verified=Depends(verify_play_integrity),
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
    model_default, model_fallback = get_model_and_fallback(
        {"temperature": 0.3}, True, premium_model, alt=True
    )
    data_queue = queue.Queue()

    def data_generator() -> Generator[str, None, None]:
        # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    # yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            try:
                conversation_manager.add_message(
                    user_id, conversation_id, data.prompt, response
                )
            except Exception as e:
                logging.error(f"Error adding message {e}")
            logging.info(f"Added ({data.prompt}, {response}) {conversation_id}")

    def run_chat() -> None:
        try:
            chat_manager.chat(
                collection_name=collection.vectordb_collection_name,
                prompt=data.prompt,
                chat_history=chat_history,
                language=data.language,
                llm=model_default,
                callback_func=callback,
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
    play_integrity_verified=Depends(verify_play_integrity),
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
    model_default, model_fallback = get_model_and_fallback(
        {"temperature": 0.3}, True, premium_model
    )
    data_queue = queue.Queue()

    class ReadDataArgs(OldBaseModel):
        query: str = OldField("all", description="What you want to search")
        subject_name: str = OldField(
            description="The name of the subject to read data from"
        )
        file_name: Optional[str] = OldField(
            None,
            description="The name of the file to read from the subject, if it is empty, the whole subject will be read/searched",
        )

    def read_vector_db(
        subject_name: str, file_name: str = None, query: str = "all"
    ) -> str:
        all_subjects = [
            collection.name
            for collection in collection_manager.get_all_by_user(user_id=user_id)
        ]
        subject_name = find_most_similar(all_subjects, subject_name, 5)

        if not subject_name:
            return "Subject name is wrong, file name might correct. Maybe list all subjects and files to find out?"

        collection = collection_manager.get_collection_by_name_and_user(
            subject_name, user_id
        )

        if collection.number_of_files == 0:
            return ("Subject has no files, but it exists",)

        if file_name:
            all_file_names = [
                file.filename
                for file in file_manager.get_all_files(
                    user_id=user_id, collection_name=subject_name
                )
            ]
            file_name = find_most_similar(all_file_names, file_name, max_distance=5)
            if not file_name:
                return "File not found. subject exists tho. Maybe list all subjects and files to find out?"

            metadata = {"file": file_name}
        else:
            metadata = {}

        docs = knowledge_manager.query_data(
            query, collection.vectordb_collection_name, k=3, metadata=metadata
        )
        data = select_random_chunks(
            "\n".join([doc.page_content for doc in docs]), 300, 600
        )
        logging.info(f"Read {data}")
        return data

    extra_tools = [
        StructuredTool.from_function(
            func=lambda subject_name, file_name=None, query="all", *args, **kwargs: read_vector_db(
                query=query, subject_name=subject_name, file_name=file_name
            ),
            name="read_user_subject_or_file",
            description="Used to read students subject of a file in that subject",
            args_schema=ReadDataArgs,
        ),
        Tool.from_function(
            func=lambda *args, **kwargs: collection_manager.get_all_files_for_user_as_string(
                user_id
            ),
            name="list_user_subjects_files",
            description="Used to list the subjects the students has added and files in them.",
        ),
    ]

    def data_generator() -> Generator[str, None, None]:
        # yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data is None:
                    # yield "[END]"
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
                extra_tools=extra_tools,
                files=collection_manager.get_all_files_for_user_as_string(user_id),
            )
        except OpenAIError as e:
            logging.error(f"Error in openai {e}")
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
            import traceback

            traceback.print_exception(e)
            logging.error(f"Error running chat in general chat: {e}")
            error_message = "Error in getting response"
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback(None)

    threading.Thread(target=run_chat).start()

    return StreamingResponse(data_generator())
