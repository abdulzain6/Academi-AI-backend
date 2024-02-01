import tempfile
from typing import Generator, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from api.config import CACHE_DOCUMENT_URL_TEMPLATE
from api.config import REDIS_URL, CACHE_DOCUMENT_URL_TEMPLATE, SEARCHX_HOST
from api.lib.database.cache_manager import RedisCacheManager
from api.lib.maths_solver.ocr import ImageOCR
from api.lib.tools import MarkdownToDocConverter, RequestsGetTool, SearchTool
from ..lib.database.messages import ConversationMetadata, MessagePair
from ..lib.utils import split_into_chunks
from ..lib.tools import (
    make_vega_graph,
    make_graphviz_graph,
)
from ..lib.inmemory_vectorstore import InMemoryVectorStore
from ..globals import (
    conversation_manager,
    chat_manager_agent_non_retrieval,
    redis_cache_manager,
    get_model_and_fallback
)
from ..dependencies import (
    can_use_premium_model,
    require_points_for_feature,
    deduct_points_for_feature,
)
from ..globals import image_ocr
from pydantic import BaseModel
from langchain.tools import StructuredTool
from langchain.utilities.searx_search import SearxSearchWrapper
from langchain.utilities.requests import TextRequestsWrapper
from langchain.schema import Document

import redis
import logging
import queue
import threading

router = APIRouter()
tools_vectorstore = InMemoryVectorStore()

class ChatGeneralInput(BaseModel):
    chat_history: Optional[list[tuple[str, str]]] = None
    prompt: str


def convert_message_pairs_to_tuples(
    message_pairs: list[MessagePair],
) -> list[tuple[str, str]]:
    return [(pair.human_message, pair.bot_response) for pair in message_pairs]

def pick_relavent_tools(tools: list[StructuredTool], query: str, k: int = 2) -> list[StructuredTool]:
    docs = [Document(page_content=tool.description, metadata={"name" : tool.name}) for tool in tools]
    tools_vectorstore.add_documents(docs)
    relavent_tools = tools_vectorstore.query_vectorstore(query=query, k=k)
    relavent_tool_names = [tool.metadata["name"] for tool in relavent_tools]
    return [tool for tool in tools if tool.name in relavent_tool_names]

@router.post("/general-chat")
def chat_general_stream(
    data: ChatGeneralInput,
):
    logging.info("Initiating chat agents")
    chat_history = data.chat_history

    model_default, model_fallback = get_model_and_fallback(
        {"temperature": 0.5}, True, False,
    )
    data_queue = queue.Queue()
    
    def make_graph(vega_lite_spec: str):
        if not vega_lite_spec:
            return "Enter a valid spec recieved none"
        try:
            return make_vega_graph(**{"vl_spec": vega_lite_spec,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE})
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

    
    must_have_tools = [
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
        MarkdownToDocConverter(
            cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
            url_template=CACHE_DOCUMENT_URL_TEMPLATE,
        ),
        RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
        StructuredTool.from_function(
            func=lambda vega_lite_spec, *args, **kwargs: make_graph(
                vega_lite_spec=vega_lite_spec
            ),
            name="make_vega_lite_graph",
            description="Used to make graphs using vega lite. Takes in a vega lite spec in json format.",
            #args_schema=MakeGraphArgs,
        ),
    ]
    
    optional_tools = []
    
    queried_tools = pick_relavent_tools(optional_tools, query=data.prompt[:600], k=2)
    logging.info(f"Picked tools: {queried_tools}")
    extra_tools = [*must_have_tools, *queried_tools]
    
    sys_template = """You are MistAI, an AI teacher designed to teach students. 
You are to take the tone of a teacher.
Talk as if you're a teacher. Use the data provided to answer user questions if its available. 
You're integrated within an app, which serves as a versatile study aid for students.
Rules:
    If you get a link from a tool, give it to the user as it is. Don't change https to sandbox!!!
    Use tools if you think you need help or to confirm answer.
    You can also use tools to give the student pdfs as study material also.
    Lets keep tools in mind before answering the questions.
    Talk like a teacher! Start the conversation with "Hello, I'm your AI teacher, ready to explore the world of knowledge together. Let's start this journey of learning and discovery!"
    use tools to better explain things, Never underestimate the power of visual aids. Use them even if not asked.
    Refuse to comment on other educational apps or institutions
    If the user asks a question, You must provide the answer step by step as if you were solving on paper
    You must return (Important):
        1. The answer to the user question in markdown.
        2. The explanation for the answer with definitions, assumptions intermediate results, units and problem statement Must explain in the easiest language as possible to a non programmer. Must be in english
        3. The step by step methodology on how the student can solve the exact same question on paper. Keep in mind the student will solve it by hand he has no tools. (Very very important)
        4. The steps must be in english and understandable.
        5. Mathematical steps also if applicable Also return what rules, formulas you use.
    
Follow all above rules (Important)"""

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
        ...

    def run_chat() -> None:
        try:
            chat_manager_agent_non_retrieval.run_agent(
                prompt=data.prompt,
                chat_history=chat_history,
                language="",
                llm=model_default,
                callback=callback,
                on_end_callback=on_end_callback,
                extra_tools=extra_tools,
                files="",
                sys_template=sys_template,
                prompt_args={}
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

@router.post("/ocr_image")
def ocr_image_route(
    file: UploadFile = File(...),
) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name
            ocr_result = image_ocr.ocr_image(temp_file_path)
        return ocr_result

    except Exception as e:
        logging.error(f"Error in ocr {e}")
        raise HTTPException(400, f"Error: {e}") from e