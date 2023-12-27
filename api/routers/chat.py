import logging
import queue
import random
import threading
from typing import Generator, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from api.lib.database.collections import CollectionModel
from api.lib.presentation_maker.image_gen import PexelsImageSearch
from ..lib.cv_maker.cv_maker import CVMaker
from ..lib.cv_maker.template_loader import template_loader
from api.lib.presentation_maker.presentation_maker import PresentationMaker
from api.lib.uml_diagram_maker import AIPlantUMLGenerator
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
)
from ..globals import (
    template_manager,
    temp_knowledge_manager,
    get_model,
    get_model_and_fallback,
)
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks, extract_schema_fields, timed_random_choice
from ..dependencies import (
    can_use_premium_model,
    require_points_for_feature,
    deduct_points_for_feature,
    use_feature_with_premium_model_check,
)
from pydantic import BaseModel
from openai import OpenAIError
from langchain.tools import StructuredTool
from .utils import select_random_chunks, find_most_similar
from langchain.pydantic_v1 import BaseModel as OldBaseModel
from langchain.pydantic_v1 import Field as OldField
from ..lib.tools import (
    MakePresentationInput,
    make_ppt,
    make_uml_diagram,
    make_cv_from_string,
    make_vega_graph,
    make_graphviz_graph,
    create_link_file
)
from api.config import CACHE_DOCUMENT_URL_TEMPLATE
from api.dependencies import can_add_more_data


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
        {"temperature": 0.3}, True, premium_model, alt=True,
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
        {"temperature": 0.3}, True, premium_model, alt=True,
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
        {"temperature": 0.5}, True, premium_model,
    )
    data_queue = queue.Queue()

    random_template = timed_random_choice(
        CVMaker.get_all_templates_static(template_loader())
    )

    class MakeFileArgs(OldBaseModel):
        subject_name: str = OldField(description="THe subject to add file to")
        filename: str = OldField(description="The name of the file to add")
        url: str = OldField(description="The url to create file from. Must be a working url you can find urls using search. example.com or any wrong url will cause fatal error!")
        
    class MakeSubjectArgs(OldBaseModel):
        name: str = OldField(description="Name of the subject to create")
        description: str = OldField(description="Description of the subject to create")

    class MakeCVArgs(OldBaseModel):
        cv_details_text: str = OldField(
            "random CV",
            description="Details of the CV formatted as short text, it must have the following user details ask them if needed:\n "
            + extract_schema_fields(random_template["schema"]),
        )

    class MakeUMLArgs(OldBaseModel):
        detailed_instructions: str = OldField(
            "random diagram", description="Details of the diagram to make"
        )

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

        llm = get_model({"temperature": 0.3}, False, premium_model)
        ppt_pages = (
            subscription_manager.get_feature_value(user_id, "ppt_pages").main_data or 12
        )
        number_of_pages = min(number_of_pages, ppt_pages)

        presentation_maker = PresentationMaker(
            template_manager,
            temp_knowledge_manager,
            llm,
            pexel_image_gen_cls=PexelsImageSearch,
            image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
            vectorstore=knowledge_manager,
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

    def make_uml_digram(detailed_instructions: str):
        logging.info(f"Making uml diagram on {detailed_instructions}")
        model_name, premium_model = can_use_premium_model(user_id=user_id)
        model = get_model({"temperature": 0}, False, premium_model, alt=False)
        uml_maker = AIPlantUMLGenerator(model, generator=plantuml_server)
        logging.info(f"UML request from {user_id}, Data: {detailed_instructions}")
        try:
            return deduct_points_for_feature(
                user_id,
                make_uml_diagram,
                func_kwargs={
                    "uml_maker": uml_maker,
                    "prompt": detailed_instructions,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                },
                feature_key="UML",
                usage_key="UML",
            )
        except Exception as e:
            logging.error(f"Error in uml diagram {e}")
            return f"Error in uml diagram {e}"

    def make_cv(string: str, template_name: str):
        if not string:
            string = "Make a random cv"
        logging.info(f"Making cv for text {string}")
        model_name, premium_model = can_use_premium_model(user_id=user_id)
        model = get_model({"temperature": 0}, False, premium_model, alt=False)
        cv_maker = CVMaker(
            templates=template_loader(),
            chrome_path="/usr/bin/google-chrome",
            chat_model=model,
        )
        try:
            return deduct_points_for_feature(
                user_id,
                make_cv_from_string,
                func_kwargs={
                    "cv_maker": cv_maker,
                    "template_name": template_name,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                    "string": string + "\n Make things up if needed keep it detailed.",
                },
                feature_key="CV",
                usage_key="CV",
            )
        except Exception as e:
            logging.error(f"Error in cv generation {e}")
            return f"Error in cv generation {e}"

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

    def create_subject(name: str, description: str):
        try:
            can_add_more_data(user_id, collection_check=True, file_check=False)
        except Exception as e:
            return "User cannot add more subjects, ask them to upgrade to PRO or elite plan."
        
        uid = str(uuid.uuid4())
        try:
            added_collection = collection_manager.add_collection(
                CollectionModel(
                    user_uid=user_id,
                    name=name,
                    description=description,
                    collection_uid=uid,
                    vectordb_collection_name=f"{user_id}_{uid}",
                )
            )
            return "Subject created successfully, lets proceed with adding files to it. AI can add using youtube links or urls only. For documents user has to enter manually."
        except Exception as e:
            return f"Error creating subject {e}"
        
    def create_file(subject_name: str, filename: str, url: str):
        try:
            return create_link_file(
                user_id=user_id,
                subject_name=subject_name,
                filename=filename,
                youtube_link=None,
                web_link=url
            )
        except Exception as e:
            return f"Error: {e}"

    extra_tools = [
        StructuredTool.from_function(
            func=lambda subject_name, filename, url, *args, **kwargs: create_file(
                subject_name=subject_name, filename=filename, url=url
            ),
            name="create_file",
            description="Used to create a file for the student from a url, or youtube link. Documents will have to be added manually by the student though. The files can be read by AI and can be used to make notes",
            args_schema=MakeFileArgs,
        ),
        StructuredTool.from_function(
            func=lambda name, description = "", *args, **kwargs: create_subject(
                name=name, description=description
            ),
            name="create_subject",
            description="Used to create a subject for the student",
            args_schema=MakeSubjectArgs,
        ),
        StructuredTool.from_function(
            func=lambda topic, instructions="", number_of_pages=5, negative_prompt="", *args, **kwargs: make_presentation(
                topic,
                instructions,
                number_of_pages,
                negative_prompt,
            ),
            name="make_ppt",
            description="Used to make ppt using AI",
            args_schema=MakePptArgs,
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
            func=lambda detailed_instructions="Random", *args, **kwargs: make_uml_digram(
                detailed_instructions=detailed_instructions
            ),
            name="make_uml_diagram",
            description="Used to make uml diagrams using AI",
            args_schema=MakeUMLArgs,
        ),
        StructuredTool.from_function(
            func=lambda *args, **kwargs: collection_manager.get_all_files_for_user_as_string(
                user_id
            ),
            name="list_user_subjects_files",
            description="Used to list the subjects the students has added and files in them.",
        ),
        StructuredTool.from_function(
            func=lambda *args, **kwargs: make_cv(
                template_name=random_template["name"],
                string=args[0] if args else kwargs.get("cv_details_text"),
            ),
            name="make_cv",
            description="Used to make a cv, Ask the user for details if needed. You can make things up except for the image url",
            args_schema=MakeCVArgs,
        ),
        StructuredTool.from_function(
            func=lambda vega_lite_spec, *args, **kwargs: make_graph(
                vega_lite_spec=vega_lite_spec
            ),
            name="make_vega_lite_graph",
            description="Used to make graphs using vega lite. Takes in a vega lite spec in json format.",
            #args_schema=MakeGraphArgs,
        ),
        StructuredTool.from_function(
            func=lambda dot_code, *args, **kwargs: create_graphviz_graph(
                dot_code=dot_code
            ),
            name="make_graphviz_graph",
            description="Used to make graphs using graphviz. Takes in valid dot language code for graphviz",
            #args_schema=MakeGraphArgs,
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
