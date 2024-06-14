import logging
import os
import re
import tempfile
from typing import List
from api.config import CACHE_DOCUMENT_URL_TEMPLATE
from api.dependencies import require_points_for_feature
from api.lib.assignment_solver import AssignmentSolver
from api.lib.tools import SearchImage, SearchTool, ScholarlySearchRun, RequestsGetTool, make_uml_diagram, make_vega_graph, make_graphviz_graph
from fastapi import APIRouter, Response, UploadFile, Depends, HTTPException
from api.globals import SEARCHX_HOST, get_model_and_fallback, plantuml_server, redis_cache_manager, client, subscription_manager
from ..auth import get_user_id, verify_play_integrity
from langchain_community.utilities.searx_search import SearxSearchWrapper
from langchain_community.utilities.requests import TextRequestsWrapper
from langchain_core.tools import tool
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
    
    solver_llm, _ = get_model_and_fallback({"temperature" : 0}, False, True, alt=True)
    extractor_llm, _ = get_model_and_fallback({"temperature" : 0}, False, True, alt=True)

    @tool
    def make_graph(vega_lite_spec: str):
        """ Used to make graphs using vega lite. Takes in a vega lite spec in json format. Returns a link"""
        if not vega_lite_spec:
            return "Enter a valid spec recieved none"
        try:
            return make_vega_graph(
                **{
                    "vl_spec": vega_lite_spec,
                    "cache_manager": redis_cache_manager,
                    "url_template": CACHE_DOCUMENT_URL_TEMPLATE,
                },
            )
        except Exception as e:
            logging.error(f"Error in graph generation {e}")
            return f"Error in graph generation {e}"
    
    @tool
    def create_graphviz_graph(dot_code: str):
        """ Used to make graphs using graphviz. Takes in valid dot language code for graphviz it must be in string no extra args. Returns a link"""
        if not dot_code:
            return "Enter valid graphviz dot code"
        try:
            return make_graphviz_graph(dot_code, cache_manager=redis_cache_manager, url_template=CACHE_DOCUMENT_URL_TEMPLATE)
        except Exception as e:
            logging.error(f"Error in graph generation {e}")
            return f"Error in graph generation {e}"

    def extract_python_code(text: str) -> List[str]:
        """
        Extract Python code blocks from a given text.

        Parameters:
            text (str): The input text containing Python code blocks.

        Returns:
            List[str]: A list of Python code blocks.
        """
        # Regular expression to match Python code blocks enclosed in triple backticks
        pattern = r"```python\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        joined_matches = "\n".join(matches)
        return joined_matches or text.strip()
    
    @tool
    def python(code: str):
        """"
Used to execute multiline python code wont persist states so run everything once.
Do not pass in Markdown just a normal python string (Important)
Try to run all the code at once
        """
        result = client.evaluate_code(extract_python_code(code))
        try:
            return result["result"]
        except Exception as e:
            return result

    try:
        solver = AssignmentSolver(
            extractor_llm,
            llm_solver=solver_llm,
            solver_tools=[
                SearchTool(
                    seachx_wrapper=SearxSearchWrapper(searx_host=SEARCHX_HOST, unsecure=True, k=3),
                ),
                ScholarlySearchRun(),
                RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
                make_graph,
                create_graphviz_graph,
                python
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
    
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=Solution.docx"}
    )
