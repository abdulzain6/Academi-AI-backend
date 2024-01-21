import logging
import queue
import tempfile
import threading
from typing import Generator, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from api.lib.maths_solver.agent import MathSolver
from ..dependencies import get_model_and_fallback, require_points_for_feature
from ..lib.database.messages import MessagePair
from ..lib.utils import split_into_chunks
from ..globals import image_ocr, conversation_manager
from ..globals import (
    client
)
from pydantic import BaseModel
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import use_feature, can_use_premium_model
from langchain.chat_models.openai import ChatOpenAI
from openai import OpenAIError



router = APIRouter()


class MathsSolveInput(BaseModel):
    question: str
    chat_history: Optional[list[tuple[str, str]]] = None


def convert_message_pairs_to_tuples(
    message_pairs: list[MessagePair],
) -> list[tuple[str, str]]:
    return [(pair.human_message, pair.bot_response) for pair in message_pairs]


@router.post("/solve_maths_stream")
@require_points_for_feature("CHAT")
def solve_maths_stream(
    maths_solver_input: MathsSolveInput,
    conversation_id: Optional[str] = None,
    user_id: str = Depends(get_user_id),
    play_integrity_verified = Depends(verify_play_integrity)
):
    logging.info(f"Got maths solver request, {user_id}... Input: {maths_solver_input}")

    if conversation_id and not conversation_manager.conversation_exists(
        user_id, conversation_id
    ):
        logging.error(f"Conversation not found {user_id}")
        raise HTTPException(
            detail="Conversation not found", status_code=status.HTTP_400_BAD_REQUEST
        )

    chat_history = (
        convert_message_pairs_to_tuples(
            conversation_manager.get_messages(user_id, conversation_id)
        )
        if conversation_id
        else maths_solver_input.chat_history
    ) or []
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)        
    model_default, model_fallback  = get_model_and_fallback({"temperature": 0}, True, premium_model)
    logging.info(f"Default {model_default}, Fallback {model_fallback}")
    if type(model_default) is ChatOpenAI:
        functions = True
    else:
        functions = False
        
    data_queue = queue.Queue()

    def callback(data: str) -> None:
        data_queue.put(data)

    def on_end_callback(response: str) -> None:
        if conversation_id:
            conversation_manager.add_message(
                user_id, conversation_id, maths_solver_input.question, response
            )

    def data_generator() -> Generator[str, None, None]:
        yield "[START]"
        while True:
            try:
                data = data_queue.get(timeout=60)
                if data == "@@END@@":
                    yield "[END]"
                    break
                yield data
            except queue.Empty:
                yield "[TIMEOUT]"
                break

    def run_agent() -> None:
        try:
            maths_solver = MathSolver(
                client,
                llm=model_default,
                is_openai_functions=functions,
            )
            maths_solver.run_agent(
                maths_solver_input.question,
                callback=callback,
                chat_history=chat_history,
                on_end_callback=on_end_callback,
            )
        except OpenAIError:
            try:
                maths_solver = MathSolver(
                    client,
                    llm=model_fallback,
                    is_openai_functions=True,
                )
                maths_solver.run_agent(
                    maths_solver_input.question,
                    callback=callback,
                    chat_history=chat_history,
                    on_end_callback=on_end_callback,
                )
            except Exception as e:
                logging.error(f"Error in math solver {user_id}, Error: {e}")
                error_message = "The AI was not able to solve the question please make your question clearer."
                for chunk in split_into_chunks(error_message, 4):
                    callback(chunk)
                callback("@@END@@")
        except Exception as e:
            logging.error(f"Error in math solver {user_id}, Error: {e}")
            error_message = "The AI was not able to solve the question please make your question clearer."
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback("@@END@@")

    threading.Thread(target=run_agent).start()

    return StreamingResponse(data_generator())


@router.post("/ocr_image")
@require_points_for_feature("OCR", "OCR")
def ocr_image_route(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    play_integrity_verified=Depends(verify_play_integrity)
) -> Optional[str]:
    logging.info(f"Got ocr request, {user_id}")
    use_feature("OCR", user_id)

    try:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name
            ocr_result = image_ocr.ocr_image(temp_file_path)
        logging.info(f"Successfully ocred {user_id}")
        return ocr_result

    except Exception as e:
        logging.error(f"Error in ocr {e}")
        raise HTTPException(400, f"Error: {e}") from e
