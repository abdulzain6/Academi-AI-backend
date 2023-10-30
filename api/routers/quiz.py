from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id, verify_play_integrity
from ..globals import file_manager, collection_manager, global_chat_model, global_chat_model_kwargs
from pydantic import BaseModel
from ..dependencies import require_points_for_feature, can_use_premium_model, use_feature_with_premium_model_check
from ..lib.quiz import QuizGenerator, UserResponse, Result
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
@require_points_for_feature("QUIZ")
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
        files = file_manager.get_file_by_name(
            user_id, quiz_input.collection_name, quiz_input.file_name
        )
    else:
        logging.error(f"File not exists {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    
    model_name, premium_model = use_feature_with_premium_model_check(user_id=user_id, feature_name="QUIZ")     
    kwargs = {**global_chat_model_kwargs}
    if model_name:
        kwargs["model"] = model_name
        
    kwargs["temperature"] = 0.5    
    
    logging.info(f"Using model {model_name} to make quiz for user {user_id}")
    
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        global_chat_model,
        kwargs,
    )
    
    try:
        questions = quiz_generator.generate_quiz(
            data,
            quiz_input.number_of_questions,
            collection_name=quiz_input.collection_name,
        )
    except Exception as e:
        logging.error(f"Error generating quiz, Error: {e}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    logging.info(f"Quiz generated, {user_id}")
    return {"questions": [question.model_dump() for question in questions]}


@router.post("/evaluate", response_model=Result)
def evaluate_quiz(
    user_answers: list[UserResponse],
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got quiz evaluation request, {user_id}... Input: {user_answers}")
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        global_chat_model,
        **global_chat_model_kwargs,
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
        files = file_manager.get_file_by_name(
            user_id, fc_input.collection_name, fc_input.file_name
        )
    else:
        logging.error(f"File not found, {user_id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File not found!")

    data = "\n".join([file.file_content for file in files if file])
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    kwargs = {**global_chat_model_kwargs}
    
    if model_name:
        kwargs["model"] = model_name
        
    kwargs["temperature"] = 0.5    
    logging.info(f"Using model {model_name} to make quiz for user {user_id}")
    
    quiz_generator = QuizGenerator(
        file_manager,
        None,
        global_chat_model,
        kwargs,
    )
    try:
        questions = quiz_generator.generate_flashcards(
            data,
            fc_input.number_of_flashcards,
            collection_name=fc_input.collection_name,
        )
        logging.info(f"Flashcards generated, {user_id}")
    except Exception as e:
        logging.error(f"Error in flash card generation. {e}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Error: {str(e)}"
        ) from e

    return {"flashcards": [flashcards.model_dump() for flashcards in questions]}
