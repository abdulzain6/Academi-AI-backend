from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id, verify_play_integrity
from ..globals import file_manager, collection_manager
from pydantic import BaseModel
from ..dependencies import get_model, require_points_for_feature, can_use_premium_model, use_feature_with_premium_model_check
from ..lib.quiz import QuizGenerator, UserResponse
from .utils import select_random_chunks
import logging

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
@require_points_for_feature("QUIZ", "QUIZ")
def make_quiz(
    quiz_input: MakeQuizInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got quiz generation request, {user_id}... Input: {quiz_input}")

    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            quiz_input.collection_name, user_id
        )
    ):
        logging.error(f"Collection {quiz_input.collection_name} does not exist, {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Collection not found!")

    if not quiz_input.file_name:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=quiz_input.collection_name
        )
    elif file_manager.file_exists(
        user_id, collection.collection_uid, quiz_input.file_name
    ):
        file = file_manager.get_file_by_name(
            user_id, quiz_input.collection_name, quiz_input.file_name
        )
        files = [file]
    else:
        logging.error(f"File not exists {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    if not data:
        data = f"Make quiz about '{quiz_input.collection_name}' if the term doesnt make sense make general quiz on the world"
    
    model_name, premium_model = use_feature_with_premium_model_check(user_id=user_id, feature_name="QUIZ")     
    model = get_model({"temperature": 0}, False, premium_model, alt=False)    
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        model
    )
    
    try:
        questions = quiz_generator.generate_quiz(
            select_random_chunks(data, 300, 1000),
            quiz_input.number_of_questions,
            collection_name=quiz_input.collection_name,
            collection_description=collection.description
        )
    except Exception as e:
        logging.error(f"Error generating quiz, Error: {e}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    quiz = {"questions": [question.dict() for question in questions]}
    logging.info(f"quiz made {quiz}")
    return quiz

@router.post("/evaluate")
def evaluate_quiz(
    user_answers: list[UserResponse],
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got quiz evaluation request, {user_id}... Input: {user_answers}")
    model = get_model({"temperature": 0.3}, False, False, alt=False)
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        model
    )
    
    try:
        return quiz_generator.evaluate_quiz(user_answers)
    except Exception as e:
        logging.error(f"Error evaluating quiz, User: {user_id}, Error: {e}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e


@router.post("/flashcards")
@require_points_for_feature("FLASHCARDS")
def make_flashcards(
    fc_input: MakeFlashCardsInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got flashcard generation request, {user_id}... Input: {fc_input}")

    if not (
        collection := collection_manager.get_collection_by_name_and_user(
            fc_input.collection_name, user_id
        )
    ):
        logging.error(f"Collection {fc_input.collection_name} does not exist, {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Collection not found!")

    if not fc_input.file_name:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=fc_input.collection_name
        )
    elif file_manager.file_exists(
        user_id, collection.collection_uid, fc_input.file_name
    ):
        file = file_manager.get_file_by_name(
            user_id, fc_input.collection_name, fc_input.file_name
        )
        files = [file]
    else:
        logging.error(f"File not found, {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    if not data:
        data = f"Make flashcards about '{fc_input.collection_name}' if the term doesnt make sense make general flashcards on the world"
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    model = get_model({"temperature": 0}, False, premium_model, alt=True)
    
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        model
    )
    try:
        questions = quiz_generator.generate_flashcards(
            select_random_chunks(data, 300, 1000),
            fc_input.number_of_flashcards,
            collection_name=fc_input.collection_name,
            collection_description=collection.description
        )
        logging.info(f"Flashcards generated, {user_id}")
    except Exception as e:
        logging.error(f"Error in flash card generation. {e}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    logging.info(f"Generated flashcards: {questions}")
    return {"flashcards": [flashcards.dict() for flashcards in questions]}
