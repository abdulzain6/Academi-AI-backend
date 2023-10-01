import queue
import tempfile
import threading
from typing import Generator, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..decorators import require_points_for_feature
from ..lib.models import MessagePair
from ..auth import get_user_id
from ..lib.utils import split_into_chunks
from ..globals import maths_solver, image_ocr, conversation_manager
from pydantic import BaseModel


router = APIRouter()


class MathsSolveInput(BaseModel):
    question: str
    model_name: str = "gpt-3.5-turbo"
    chat_history: Optional[list[tuple[str, str]]] = None


def convert_message_pairs_to_tuples(
    message_pairs: list[MessagePair],
) -> list[tuple[str, str]]:
    return [(pair.human_message, pair.bot_response) for pair in message_pairs]


@router.post("/solve_maths_stream")
def solve_maths_stream(
    maths_solver_input: MathsSolveInput,
    conversation_id: Optional[str] = None,
    user_id: str = Depends(get_user_id),
    _=Depends(require_points_for_feature("CHAT")),
) -> StreamingResponse:
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
        else maths_solver_input.chat_history
    ) or []

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
            maths_solver.run_agent(
                maths_solver_input.question,
                structured=False,
                stream=True,
                model_name=maths_solver_input.model_name,
                callback=callback,
                chat_history=chat_history,
                on_end_callback=on_end_callback,
            )
        except Exception as e:
            print(e)
            error_message = "The AI was not able to solve the question please make your question clearer."
            for chunk in split_into_chunks(error_message, 4):
                callback(chunk)
            callback("@@END@@")

    threading.Thread(target=run_agent).start()

    return StreamingResponse(data_generator())


@router.post("/ocr_image")
def ocr_image_route(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    _=Depends(require_points_for_feature("OCR")),
) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name
            ocr_result = image_ocr.ocr_image(temp_file_path)

        return ocr_result

    except Exception as e:
        raise HTTPException(400, f"Error: {e}") from e
