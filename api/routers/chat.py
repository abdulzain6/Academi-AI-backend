from typing import Generator, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.lib.database.collections import CollectionModel
from api.lib.diagram_maker import DiagramMaker
from api.lib.presentation_maker.image_gen import PexelsImageSearch
from ..lib.cv_maker.cv_maker import CVMaker
from ..lib.cv_maker.template_loader import template_loader
from api.lib.presentation_maker.presentation_maker import PresentationMaker
from api.lib.uml_diagram_maker import AIPlantUMLGenerator
from api.config import CACHE_DOCUMENT_URL_TEMPLATE
from api.dependencies import can_add_more_data
from ..lib.notes_maker import make_notes_maker, get_available_note_makers
from api.config import REDIS_URL, CACHE_DOCUMENT_URL_TEMPLATE, SEARCHX_HOST
from api.lib.database.cache_manager import RedisCacheManager
from api.lib.tools import ScholarlySearchRun, MarkdownToDocConverter, RequestsGetTool, SearchTool, SearchImage
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks, extract_schema_fields, timed_random_choice
from ..lib.tools import (
    MakePresentationInput,
    make_ppt,
    make_uml_diagram,
    make_cv_from_string,
    make_vega_graph,
    make_graphviz_graph,
    create_link_file,
    make_notes,
    write_content
)
from ..lib.writer import Writer
from ..lib.inmemory_vectorstore import InMemoryVectorStore
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    collection_manager,
    chat_manager,
    file_manager,
    conversation_manager,
    chat_manager_agent_non_retrieval,
    knowledge_manager,
    subscription_manager,
    redis_cache_manager,
    plantuml_server,
    template_manager,
    temp_knowledge_manager,
    get_model,
    get_model_and_fallback
)
from ..dependencies import (
    can_use_premium_model,
    require_points_for_feature,
    deduct_points_for_feature,
    use_feature_with_premium_model_check,
)
from .utils import select_random_chunks, find_most_similar
from pydantic import BaseModel
from openai import OpenAIError
from langchain.tools import StructuredTool
from langchain.pydantic_v1 import BaseModel as OldBaseModel
from langchain.pydantic_v1 import Field as OldField
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_community.tools.youtube.search import YouTubeSearchTool
from langchain_community.utilities.requests import TextRequestsWrapper
from langchain.schema import Document

import redis
import logging
import queue
import random
import threading
import uuid

router = APIRouter()
tools_vectorstore = InMemoryVectorStore()



class ChatGeneralInput(BaseModel):
    chat_history: Optional[List[Tuple[str, str]]] = None
    prompt: str
    language: str = "English"

class ChatCollectionInput(BaseModel):
    collection_name: str
    chat_history: Optional[List[Tuple[str, str]]] = None
    prompt: str
    language: str = "English"

class ChatFileInput(ChatCollectionInput):
    file_name: str

class SubjectMissingException(Exception):
    pass


def convert_message_pairs_to_tuples(
    message_pairs: List[MessagePair],
) -> List[Tuple[str, str]]:
    return [(pair.human_message, pair.bot_response) for pair in message_pairs]

def pick_relavent_tools(tools: List[StructuredTool], query: str, k: int = 2) -> List[StructuredTool]:
    docs = [Document(page_content=tool.description, metadata={"name" : tool.name}) for tool in tools]
    tools_vectorstore.add_documents(docs)
    relavent_tools = tools_vectorstore.query_vectorstore(query=query, k=k)
    relavent_tool_names = [tool.metadata["name"] for tool in relavent_tools]
    return [tool for tool in tools if tool.name in relavent_tool_names]
    
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
                metadata={"user" : user_id},
                collection_name=collection.name,
                prompt=data.prompt,
                chat_history=chat_history,
                llm=model_default,
                callback_func=callback,
                on_end_callback=on_end_callback,
                help_data_random=chat_manager.read_file_contents(
                    user_id=user_id,
                    collection_name=collection.name,
                    file_manager=file_manager,
                )
            )
        except OpenAIError:
            try:
                chat_manager.chat(
                    metadata={"user" : user_id},
                    collection_name=collection.name,
                    prompt=data.prompt,
                    chat_history=chat_history,
                    llm=model_fallback,
                    callback_func=callback,
                    on_end_callback=on_end_callback,
                    help_data_random=chat_manager.read_file_contents(
                        user_id=user_id,
                        collection_name=collection.name,
                        file_manager=file_manager,
                    )
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
                collection_name=collection.name,
                metadata={"user" : user_id},
                prompt=data.prompt,
                chat_history=chat_history,
                llm=model_default,
                callback_func=callback,
                on_end_callback=on_end_callback,
                filename=data.file_name,
                help_data_random=chat_manager.read_file_contents(
                    user_id=user_id,
                    collection_name=collection.name,
                    file_manager=file_manager,
                    file_name=data.file_name
                )
            )
        except OpenAIError:
            try:
                chat_manager.chat(
                    metadata={"user" : user_id},
                    collection_name=collection.name,
                    prompt=data.prompt,
                    chat_history=chat_history,
                    llm=model_fallback,
                    callback_func=callback,
                    on_end_callback=on_end_callback,
                    filename=data.file_name,
                    help_data_random=chat_manager.read_file_contents(
                        user_id=user_id,
                        collection_name=collection.name,
                        file_manager=file_manager,
                        file_name=data.file_name
                    )
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
        {"temperature": 0.5}, True, premium_model, alt=False
    )
    data_queue = queue.Queue()

    class WriterArgs(OldBaseModel):
        topic: str = OldField(
            None,
            description="The Topic to write on"
        )
        to_generate: Optional[str] =  OldField(
            "Essay",
            description="The content to write. Can be essays, articles or anything"
        )
        negative_prompt: Optional[str] = ""
        minimum_word_count: Optional[int] = 100
        instructions: Optional[str] = "Be detailed"
    
    class MakeNotesArgs(OldBaseModel):
        instructions: str = OldField("")
        template: str = OldField(
            random.choice(get_available_note_makers()),
            description=f"Template to make notes from, Available: {get_available_note_makers()}"
        )
        link: str = OldField("", description="The link to make notes from. Web or youtube link.")

    class ReadDataArgs(OldBaseModel):
        query: str = OldField("all", description="What you want to search")
        subject_name: str = OldField(
            description="The name of the subject to read data from"
        )
        file_name: Optional[str] = OldField(
            None,
            description="The name of the file to read from the subject, if it is empty, the whole subject will be read/searched",
        )

    class MakePptArgs(OldBaseModel):
        topic: str = OldField(
            ..., description="The main subject or title of the presentation."
        )
        instructions: str = OldField(
            ...,
            description="Specific guidelines or directives for creating the presentation content.",
        )
        number_of_pages: int = OldField(
            ..., description="The desired number of pages/slides in the presentation."
        )
        negative_prompt: str = OldField(
            ...,
            description="Any themes, topics, or elements that should be avoided in the presentation.",
        )
        subject_name: Optional[str] = OldField(
            None, description="Name of users subject to make ppt from"
        )
        files: Optional[List[str]] = OldField(
            None,
            description="An optional list of file names from the subject to make ppt from",
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
            return "Subject has no files, but it exists. Ask the user to upload a file. AI can also use its own knowledge to answer. Or create files"

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

        metadata["collection"] = collection.name
        metadata["user"] = user_id
        docs = knowledge_manager.query_data(query, k=3, metadata=metadata)
        data = select_random_chunks(
            "\n".join([doc.page_content for doc in docs]), 300, 600
        )
        if not data:
            logging.info("Using random file data")
            data = chat_manager.read_file_contents(
                user_id=user_id,
                collection_name=collection.name,
                file_manager=file_manager,
                length=1000
            )
        logging.info(f"Read {data}")
        return f"""
File Content:
=======
{data}
======="""

    def make_presentation(
        topic: str,
        instructions: str,
        number_of_pages: int,
        negative_prompt: str,
    ):
        logging.info(f"{topic}, {instructions}, {number_of_pages}, {negative_prompt}")
        try:
            model_name, premium_model = use_feature_with_premium_model_check(
                "PRESENTATION", user_id=user_id
            )
        except Exception:
            return "Limit reached user cannot make more ppts"

        llm = get_model({"temperature": 0.3}, False, premium_model, alt=True, json_mode=True)
        ppt_pages = (
            subscription_manager.get_feature_value(user_id, "ppt_pages").main_data or 12
        )
        number_of_pages = min(number_of_pages, ppt_pages)

        presentation_maker = PresentationMaker(
            template_manager,
            temp_knowledge_manager,
            llm,
            vectorstore=knowledge_manager,
            diagram_maker=DiagramMaker(None, llm, None)
        )
        try:
            return deduct_points_for_feature(
                user_id,
                make_ppt,
                func_kwargs={
                    "ppt_maker": presentation_maker,
                    "ppt_input": MakePresentationInput(
                        topic=topic,
                        instructions=instructions,
                        number_of_pages=number_of_pages,
                        negative_prompt=negative_prompt,
                        collection_name=None,
                        files=None,
                    ),
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                },
                feature_key="PRESENTATION",
                usage_key="PRESENTATION",
            )
        except Exception as e:
            logging.error(f"Error in ppt {e}")
            return f"Error in ppt {e}"

    def make_graph(vega_lite_spec: str):
        if not vega_lite_spec:
            return "Enter a valid spec recieved none"
        try:
            return deduct_points_for_feature(
                user_id,
                make_vega_graph,
                func_kwargs={
                    "vl_spec": vega_lite_spec,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                },
                feature_key="GRAPH",
                usage_key="GRAPH",
            )
        except Exception as e:
            logging.error(f"Error in graph generation {e}")
            return f"Error in graph generation {e}"

    def create_graphviz_graph(dot_code: str):
        if not dot_code:
            return "Enter valid graphviz dot code"
        try:
            return make_graphviz_graph(dot_code, cache_manager=redis_cache_manager, url_template=CACHE_DOCUMENT_URL_TEMPLATE)
        except Exception as e:
            logging.error(f"Error in graph generation {e}")
            return f"Error in graph generation {e}"

    def create_notes(link: str, instructions: str, template: str):
        available = get_available_note_makers()
        if template not in available:
            return f"Chosen Template not available. Available templates: {available}"
        
        try:
            data, _, _ = knowledge_manager.load_web_youtube_link({}, None, web_url=link, injest=False)
        except Exception as e:
            logging.error(f"Error: {e}")
            return f"Error: {e}"

        
        content = select_random_chunks(data, 1000, 2700)
        
        try:
            model_name, premium_model = use_feature_with_premium_model_check(
                "NOTES", user_id=user_id
            )
        except Exception:
            return "Limit reached user cannot make more notes"

        llm = get_model({"temperature": 0.3}, False, premium_model, alt=True)
        try:
            return deduct_points_for_feature(
                user_id,
                make_notes,
                func_kwargs={
                    "notes_maker" : make_notes_maker(
                        maker_type=template,
                        llm=llm
                    ),
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                    "data_string" : content,
                    "instructions" : instructions
                },
                feature_key="NOTES",
                usage_key="NOTES",
            )
        except ValueError as e:
            logging.error(f"Error in making notes {e}")
            return f"Error in making notes {e}. Maybe give the user notes in docs its free?"       
        except Exception as e:
            logging.error(f"Error in making notes {e}")
            return f"Error in making notes {e}"
        
    def write_content_tool_func(topic: str, to_generate: str, negative_prompt: str, minimum_word_count: int, instructions: str):
        model_name, premium_model = can_use_premium_model(user_id=user_id)
        model = get_model({"temperature": 0}, False, premium_model, alt=True)
        writer = Writer(model)
        try:
            return deduct_points_for_feature(
                user_id,
                write_content,
                func_kwargs={
                    "writer" : writer,
                    "topic": topic,
                    "instructions": instructions,
                    "minimum_word_count": minimum_word_count,
                    "negative_prompt": negative_prompt,
                    "to_generate": to_generate,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE
                },
                feature_key="WRITER",
                usage_key="WRITER",
            )  
        except Exception as e:
            logging.error(f"Error in writing content {e}")
            return f"Error in writing content {e}"
        
        
    
    
    must_have_tools = [
        StructuredTool.from_function(
            func=lambda topic="", to_generate="content", negative_prompt="", minimum_word_count=500, instructions="", *args, **kwargs: write_content_tool_func(
                topic=topic,
                instructions=instructions,
                minimum_word_count=minimum_word_count,
                negative_prompt=negative_prompt,
                to_generate=to_generate,
            ),
            name="writer",
            description="Used to write content like poems, essays, articles, reports",
            args_schema=WriterArgs,
        ),
        StructuredTool.from_function(
            func=lambda  link="", instructions = "", template = random.choice(get_available_note_makers()), *args, **kwargs: create_notes(
                instructions=instructions,
                template=template,
                link=link
            ),
            name="make_notes_from_link",
            description="Used to make notes from links. These can be web links or youtube links",
            args_schema=MakeNotesArgs,
        ),
        StructuredTool.from_function(
            func=lambda subject_name, file_name=None, query="all", *args, **kwargs: read_vector_db(
                query=query, subject_name=subject_name, file_name=file_name
            ),
            name="read_user_subject_or_file",
            description="Used to read students subject of a file in that subject",
            args_schema=ReadDataArgs,
        ),
        StructuredTool.from_function(
            func=lambda *args, **kwargs: collection_manager.get_all_files_for_user_as_string(
                user_id
            ),
            name="list_user_subjects_files",
            description="Used to list the subjects the students has added and files in them.",
        ),
        StructuredTool.from_function(
            func=lambda dot_code, *args, **kwargs: create_graphviz_graph(
                dot_code=dot_code
            ),
            name="make_graphviz_graph",
            description="Used to make graphs using graphviz. Takes in valid dot language code for graphviz it must be in string no extra args",
            #args_schema=MakeGraphArgs,
        ),
        SearchTool(
            seachx_wrapper=SearxSearchWrapper(searx_host=SEARCHX_HOST, unsecure=True, k=3)
        ),
        SearchImage(instance_url=SEARCHX_HOST),
        MarkdownToDocConverter(
            cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
            url_template=CACHE_DOCUMENT_URL_TEMPLATE,
        ),
    ]
    
    optional_tools = [
        RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
        YouTubeSearchTool(),
        #ScholarlySearchRun(), 
        StructuredTool.from_function(
            func=lambda vega_lite_spec, *args, **kwargs: make_graph(
                vega_lite_spec=vega_lite_spec
            ),
            name="make_vega_lite_graph",
            description="Used to make graphs using vega lite. Takes in a vega lite spec in json format.",
            #args_schema=MakeGraphArgs,
        ),
        StructuredTool.from_function(
            func=lambda topic, instructions="", number_of_pages=5, negative_prompt="", *args, **kwargs: make_presentation(
                topic,
                instructions,
                number_of_pages,
                negative_prompt,
            ),
            name="make_presentation",
            description="Used to make ppt/powerpoint presentation.",
            args_schema=MakePptArgs,
        ),
    ]
    
    queried_tools = pick_relavent_tools(optional_tools, query=data.prompt[:600], k=2)
    logging.info(f"Picked tools: {queried_tools}")
    extra_tools = [*must_have_tools, *queried_tools]

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
                llm=model_default,
                callback=callback,
                on_end_callback=on_end_callback,
                extra_tools=extra_tools,
                files=collection_manager.get_all_files_for_user_as_string(user_id),
            )
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
