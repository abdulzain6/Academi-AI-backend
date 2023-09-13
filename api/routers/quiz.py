from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id
from ..globals import file_manager, quiz_generator, collection_manager
from pydantic import BaseModel
from ..config import QUIZ_MAX_API_CALLS
from ..lib.quiz import UserResponse, Result

router = APIRouter()


class MakeQuizInput(BaseModel):
    collection_name: str
    file_name: Optional[str] = None
    number_of_questions: int = 15


@router.post("/")
def make_quiz(quiz_input: MakeQuizInput, user_id=Depends(get_user_id)):
    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            quiz_input.collection_name, user_id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Collection not found!")
    
    if not quiz_input.file_name:
        files = file_manager.get_all_files(user_id=user_id, collection_name=quiz_input.collection_name)
    elif file_manager.file_exists(user_id, collection.collection_uid, quiz_input.file_name):
        files = file_manager.get_file_by_name(user_id, quiz_input.collection_name, quiz_input.file_name)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")
    
    data = "\n".join(
        [
            file.file_content
            for file in files
            if file
        ]
    )
    try:
        questions = quiz_generator.generate_quiz(data, quiz_input.number_of_questions, max_generations=QUIZ_MAX_API_CALLS)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}") from e
    
    return {"questions" : [question.model_dump() for question in questions]}

@router.post("/evaluate", response_model=Result)
def evaluate_quiz(user_answers: list[UserResponse], user_id=Depends(get_user_id)):
    try:
        return quiz_generator.evaluate_quiz(user_answers)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}") from e
