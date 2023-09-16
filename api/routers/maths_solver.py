import queue
import threading
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from ..auth import get_user_id
from ..lib.utils import split_into_chunks
from ..globals import maths_solver
from pydantic import BaseModel


router = APIRouter()


class MathsSolveInput(BaseModel):
    question: str
    model_name: str = "gpt-3.5-turbo"


@router.post("/solve_maths_json")
def solve_maths(maths_solver_input: MathsSolveInput, user_id=Depends(get_user_id)):
    try:
        for _ in range(3):
            return maths_solver.run_agent(
                maths_solver_input.question,
                structured=True,
                stream=False,
                model_name=maths_solver_input.model_name,
            )
    except Exception as e:
        print(e)
        raise HTTPException(
            400,
            detail="The AI was not able to solve the question please make your question clearer.",
        ) from e


@router.post("/solve_maths_stream")
def solve_maths_stream(
    maths_solver_input: MathsSolveInput, user_id=Depends(get_user_id)
):
    data_queue = queue.Queue()

    def callback(data):
        data_queue.put(data)

    def data_generator():
        yield "[START]"
        while True:
            data = data_queue.get(timeout=60)
            if data == "@@END@@":
                yield "[END]"
                break
            yield data

    def run_agent():
        try:
            maths_solver.run_agent(
                maths_solver_input.question,
                structured=False,
                stream=True,
                model_name=maths_solver_input.model_name,
                callback=callback,
            )
        except Exception as e:
            print(e)
            error_message = "The AI was not able to solve the question please make your question clearer."
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback("@@END@@")

    threading.Thread(target=run_agent).start()
    return StreamingResponse(data_generator())
