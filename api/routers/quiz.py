from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id
from ..globals import file_manager, quiz_generator, collection_manager
from pydantic import BaseModel
from ..decorators import require_points_for_feature
from ..lib.quiz import UserResponse, Result

router = APIRouter()


class MakeQuizInput(BaseModel):
    collection_name: str
    file_name: Optional[str] = None
    number_of_questions: int = 15


class MakeFlashCardsInput(BaseModel):
    collection_name: str
    file_name: Optional[str] = None
    number_of_flashcards: int = 10


@router.post("/")
def make_quiz(
    quiz_input: MakeQuizInput,
    user_id=Depends(get_user_id),
    _=Depends(require_points_for_feature("QUIZ")),
):
    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            quiz_input.collection_name, user_id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Collection not found!")

    if not quiz_input.file_name:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=quiz_input.collection_name
        )
    elif file_manager.file_exists(
        user_id, collection.collection_uid, quiz_input.file_name
    ):
        files = file_manager.get_file_by_name(
            user_id, quiz_input.collection_name, quiz_input.file_name
        )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    try:
        questions = quiz_generator.generate_quiz(
            data,
            quiz_input.number_of_questions,
            collection_name=quiz_input.collection_name,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    return {"questions": [question.model_dump() for question in questions]}


@router.post("/evaluate", response_model=Result)
def evaluate_quiz(user_answers: list[UserResponse], user_id=Depends(get_user_id)):
    try:
        return quiz_generator.evaluate_quiz(user_answers)
    except Exception as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e


@router.post("/flashcards")
def make_flashcards(
    fc_input: MakeFlashCardsInput,
    user_id=Depends(get_user_id),
    _=Depends(require_points_for_feature("FLASHCARDS")),
):
    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            fc_input.collection_name, user_id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Collection not found!")

    if not fc_input.file_name:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=fc_input.collection_name
        )
    elif file_manager.file_exists(
        user_id, collection.collection_uid, fc_input.file_name
    ):
        files = file_manager.get_file_by_name(
            user_id, fc_input.collection_name, fc_input.file_name
        )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    try:
        questions = quiz_generator.generate_flashcards(
            data,
            fc_input.number_of_flashcards,
            collection_name=fc_input.collection_name,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    return {"flashcards": [flashcards.model_dump() for flashcards in questions]}
