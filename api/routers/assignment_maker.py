import io
import logging
import os
import re
import tempfile
from typing import List

from fastapi.responses import StreamingResponse
from api.config import CACHE_DOCUMENT_URL_TEMPLATE
from api.dependencies import require_points_for_feature
from api.lib.assignment_solver import AssignmentSolver
from api.lib.tools import SearchImage, SearchTool, ScholarlySearchRun, RequestsGetTool, make_uml_diagram, make_vega_graph, make_graphviz_graph
from fastapi import APIRouter, Response, UploadFile, Depends, HTTPException
from api.globals import SEARCHX_HOST, get_model_and_fallback, get_model, redis_cache_manager, client, subscription_manager
from ..auth import get_user_id, verify_play_integrity
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_community.utilities.requests import TextRequestsWrapper
from langchain_core.tools import tool, StructuredTool
from api.lib.database.purchases import SubscriptionType
from fastapi import File
from pydantic import BaseModel


router = APIRouter()


class AssignmentSubmission(BaseModel):
    instructions: str
    file: UploadFile = File(...)
    
@router.post("/solve")
@require_points_for_feature("ASSIGNMENT")
def solve_assignment(
    file: UploadFile,
    instructions: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified = Depends(verify_play_integrity)
):
    if subscription_manager.get_subscription_type(user_id) in {SubscriptionType.FREE, SubscriptionType.LITE}:
        raise HTTPException(status_code=400, detail="You must be subscribed to pro or elite to use this feature.")
    
    solver_llm = get_model({"temperature" : 0}, False, True, alt=True)
    extractor_llm, _ = get_model({"temperature" : 0}, False, True, alt=True)

    def make_graph(vega_lite_spec: str) -> str:
        if not vega_lite_spec:
            return "Enter a valid spec, received none"
        try:
            return make_vega_graph(
                vl_spec=vega_lite_spec,
                cache_manager=redis_cache_manager,
                url_template=CACHE_DOCUMENT_URL_TEMPLATE,
            )
        except Exception as e:
            logging.error(f"Error in graph generation: {e}")
            return f"Error in graph generation: {e}"

    def create_graphviz_graph(dot_code: str) -> str:
        """ Used to make graphs using graphviz. Takes in valid dot language code for graphviz it must be in string, no extra args. Returns a link """
        if not dot_code:
            return "Enter valid graphviz dot code"
        try:
            return make_graphviz_graph(dot_code, cache_manager=redis_cache_manager, url_template=CACHE_DOCUMENT_URL_TEMPLATE)
        except Exception as e:
            logging.error(f"Error in graph generation: {e}")
            return f"Error in graph generation: {e}"

    def extract_python_code(text: str) -> List[str]:
        """ Extract Python code blocks from a given text. """
        pattern = r"```python\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        return "\n".join(matches) or text.strip()

    def exec_python(code: str) -> str:
        """ Used to execute multiline Python code. Won't persist states, so run everything once. """
        result = client.evaluate_code(extract_python_code(code))
        try:
            return result["result"]
        except Exception as e:
            return f"Error in code execution: {e}"

    from langchain.pydantic_v1 import BaseModel, Field
    
    class MakeGraphArgs(BaseModel):
        vega_lite_spec: str = Field(description="The vega lite spec used to make the graph")

    class CreateGraphvizGraphArgs(BaseModel):
        dot_code: str = Field(description="The graphviz dot code to generate the graph")

    class ExecPythonArgs(BaseModel):
        code: str = Field(description="The Python code to execute")

    tools = [
        StructuredTool(
            name="make_graph",
            description="Used to make graphs using vega lite. Takes in a vega lite spec in JSON format. Returns a link.",
            args_schema=MakeGraphArgs,
            func=lambda vega_lite_spec, *args, **kwargs: make_graph(vega_lite_spec=vega_lite_spec)
        ),
        StructuredTool(
            name="create_graphviz_graph",
            description="Used to make graphs using graphviz. Takes in valid dot language code for graphviz in string format. Returns a link.",
            args_schema=CreateGraphvizGraphArgs,
            func=lambda dot_code, *args, **kwargs: create_graphviz_graph(dot_code=dot_code)
        ),
        StructuredTool(
            name="exec_python",
            description="Used to execute multiline Python code. Do not pass in Markdown, just a normal Python string. Try to run all the code at once.",
            args_schema=ExecPythonArgs,
            func=lambda code, *args, **kwargs: exec_python(code=code)
        ),
    ]

    try:
        solver = AssignmentSolver(
            extractor_llm,
            llm_solver=solver_llm,
            solver_tools=[
                SearchTool(
                    seachx_wrapper=SearxSearchWrapper(searx_host=SEARCHX_HOST, unsecure=True, k=3),
                ),
                *tools
            ]
        )
        _, file_extension = os.path.splitext(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            tmp_file.write(file.file.read())
            tmp_file_path = tmp_file.name
            
            try:
                questions, images = solver.extract_questions(tmp_file_path)
            except AssertionError as e:
                raise HTTPException(status_code=400, detail=str(e))
            
            if not images or not questions:
                raise HTTPException(detail="Invalid file/ File has no questions.")
            
            logging.info(f"Questions extracted, count: {len(questions.questions_or_tasks)}")
            
            solutions = solver.solve_questions(questions, images, instructions=instructions)
            logging.info(f"Questions solved")

            md_answer = solver.format_solution(questions, solutions)
            docx_bytes = solver.markdown_to_docx(md_answer)
            logging.info(f"Converting to docx")

        try:
            os.remove(tmp_file_path)
        except Exception:
            pass
        
    except HTTPException as e:
        logging.error(f"Error in assignment maker: {e}")
        raise e
    
    except Exception as e:
        logging.error(f"Error in assignment maker: {e}")
        raise HTTPException(status_code=400, detail="Something went wrong, Try again later")
    
   # return Response(
   #     content=docx_bytes,
   #     media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    #    headers={"Content-Disposition": "attachment; filename=Solution.docx"}
    #)
    response = StreamingResponse(io.BytesIO(docx_bytes), media_type="application/octet-stream")
    response.headers[
        "Content-Disposition"
    ] = f"attachment; filename=Solution.docx"
    return response
