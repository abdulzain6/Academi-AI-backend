import logging
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import Depends, HTTPException
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    file_manager,
    template_manager,
    temp_knowledge_manager,
    knowledge_manager,
)
from ..lib.presentation_maker.presentation_maker import PresentationInput, PresentationMaker, PexelsImageSearch
from ..dependencies import get_model, require_points_for_feature, use_feature_with_premium_model_check
from langchain.chat_models import ChatOpenAI
from pydantic import BaseModel
from ..gpts_routers.auth import verify_token
from typing import Generator, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.lib.database.collections import CollectionModel
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
from ..routers.utils import select_random_chunks, find_most_similar
from pydantic import BaseModel
from openai import OpenAIError
from langchain.tools import StructuredTool
from langchain.pydantic_v1 import BaseModel as OldBaseModel
from langchain.pydantic_v1 import Field as OldField
from langchain.utilities.searx_search import SearxSearchWrapper
from langchain.tools.youtube.search import YouTubeSearchTool
from langchain.utilities.requests import TextRequestsWrapper
from langchain.schema import Document

import logging


tools_vectorstore = InMemoryVectorStore()

class ChatGeneralInput(BaseModel):
    prompt: str
    language: str = "English"

class GetTemplateResponse(BaseModel):
    templates: list[dict[str, str]]
    images: list[dict[str, str]]

class MakePresentationInput(BaseModel):
    topic: str
    instructions: str
    number_of_pages: int
    negative_prompt: str
    collection_name: Optional[str]
    files: Optional[list[str]]
    use_data: bool = True
    auto_select_template: bool = True
    template_name: Optional[str] = ""



def pick_relavent_tools(tools: list[StructuredTool], query: str, k: int = 2) -> list[StructuredTool]:
    docs = [Document(page_content=tool.description, metadata={"name" : tool.name}) for tool in tools]
    tools_vectorstore.add_documents(docs)
    relavent_tools = tools_vectorstore.query_vectorstore(query=query, k=k)
    relavent_tool_names = [tool.metadata["name"] for tool in relavent_tools]
    return [tool for tool in tools if tool.name in relavent_tool_names]

def verify_file_existance(
    user_id: str, file_names: list[str], collection_uid: str
) -> bool:
    return all(
        file_manager.file_exists(user_id, collection_uid, file_name)
        for file_name in file_names
    )


router = APIRouter()


@router.get("/templates")
def get_available_templates(_ = Depends(verify_token)):

    templates = template_manager.get_all_templates()

    return [
        {template.template_name.title(): template.template_description}
        for template in templates
    ]
    


@router.post("/")
def make_presentation(
    presentation_input: MakePresentationInput,
    _ = Depends(verify_token)
):
    llm = get_model({"temperature": 0}, False, False, cache=False, alt=False)
    ppt_pages = 12
        
    ppt_pages = max(ppt_pages, 4)
    presentation_input.number_of_pages = min(presentation_input.number_of_pages, ppt_pages)
    
    presentation_maker = PresentationMaker(
        template_manager,
        temp_knowledge_manager,
        llm,
        pexel_image_gen_cls=PexelsImageSearch,
        image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
        vectorstore=knowledge_manager,
        use_schema=False
    )
    
    coll_name = None

    if not presentation_input.auto_select_template:
        template_name = presentation_input.template_name
    else:
        template_name = None

    try:
        file_path = presentation_maker.make_presentation(
            PresentationInput(
                topic=presentation_input.topic,
                instructions=presentation_input.instructions,
                number_of_pages=presentation_input.number_of_pages,
                negative_prompt=presentation_input.negative_prompt,
                collection_name=coll_name,
                files=presentation_input.files,
                user_id=""
            ),
            template_name,
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    return FileResponse(file_path, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_path.split('/')[-1], safe='')}"})



@router.post("/chat")
def command(
    data: ChatGeneralInput,
    _ = Depends(verify_token)
):

    model_default, model_fallback = get_model_and_fallback(
        {"temperature": 0.5}, False, False,
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


    def make_presentation(
        topic: str,
        instructions: str,
        number_of_pages: int,
        negative_prompt: str,
    ):
        logging.info(f"{topic}, {instructions}, {number_of_pages}, {negative_prompt}")

        llm = get_model({"temperature": 0.3}, False, False)

        presentation_maker = PresentationMaker(
            template_manager,
            temp_knowledge_manager,
            llm,
            pexel_image_gen_cls=PexelsImageSearch,
            image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
            vectorstore=knowledge_manager,
            use_schema=False
        )
        try:
            return make_ppt(**{
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
                }
            )
 
        except Exception as e:
            logging.error(f"Error in ppt {e}")
            return f"Error in ppt {e}"

    optional_tools = [
        RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
        YouTubeSearchTool(),
        ScholarlySearchRun(), 
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
    ]
    
    queried_tools = pick_relavent_tools(optional_tools, query=data.prompt, k=2)
    logging.info(f"Picked tools: {queried_tools}")
    extra_tools = queried_tools
    resp = chat_manager_agent_non_retrieval.run_agent(
        prompt=data.prompt,
        chat_history=[],
        language=data.language,
        llm=model_default,
        callback=None,
        on_end_callback=None,
        extra_tools=extra_tools,
        files="",
    )

    return {"response" : resp}
