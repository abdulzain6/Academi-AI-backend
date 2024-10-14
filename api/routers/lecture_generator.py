import base64
import logging
import os
from io import BytesIO
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import List, Optional

from ..lib.database.purchases import SubscriptionType
from ..lib.diagram_maker import DiagramMaker
from ..globals import subscription_manager, temp_knowledge_manager, template_manager, knowledge_manager, collection_manager, file_manager, lecture_db, redis_cache_manager
from ..auth import get_user_id, verify_play_integrity
from ..lib.presentation_maker.presentation_maker import PresentationInput, PresentationMaker
from ..dependencies import get_model, can_use_premium_model, require_points_for_feature
from ..lib.runpod_caller import RunpodCaller
from ..lib.database.lectures import LectureCreate, LectureResponse, LectureStatus, LectureUpdate



router = APIRouter()


class MakeLectureInput(BaseModel):
    topic: str
    instructions: str
    negative_prompt: str
    collection_name: Optional[str]
    files: Optional[list[str]]
    use_data: bool = True
    
    
def verify_file_existance(
    user_id: str, file_names: list[str], collection_uid: str
) -> bool:
    return all(
        file_manager.file_exists(user_id, collection_uid, file_name)
        for file_name in file_names
    )
    
def background_lecture_creation(
    lecture_id: str,
    user_id: str,
    lecture_input: MakeLectureInput,
    model_name: str,
    premium_model: bool,
    ppt_pages: int
):
    try:
        llm = get_model({"temperature": 0}, False, True, premium_model, cache=False)
        
        logging.info(f"Using model {model_name} to make presentation for user {user_id}")
        presentation_maker = PresentationMaker(
            template_manager,
            temp_knowledge_manager,
            llm,
            vectorstore=knowledge_manager,
            diagram_maker=DiagramMaker(None, llm, None)
        )
        
        coll_name = None
        if lecture_input.use_data and lecture_input.collection_name:
            collection = collection_manager.get_collection_by_name_and_user(
                lecture_input.collection_name, user_id
            )
            if collection:
                coll_name = collection.name
                if lecture_input.files and not verify_file_existance(
                    user_id, lecture_input.files, collection.collection_uid
                ):
                    raise ValueError("Some files don't exist")
            else:
                raise ValueError("Collection does not exist")

        file_path, content = presentation_maker.make_presentation(
            PresentationInput(
                topic=lecture_input.topic,
                instructions=lecture_input.instructions,
                number_of_pages=ppt_pages,
                negative_prompt=lecture_input.negative_prompt,
                collection_name=coll_name,
                files=lecture_input.files,
                user_id=user_id
            ),
            None,
        )

        logging.info(f"Presentation made successfully! {user_id}")
        logging.info(f"Presentation path: {file_path}")
        
        with open(file_path, "rb") as file:
            ppt_b64 = base64.b64encode(file.read()).decode("utf-8")
        
        caller = RunpodCaller(
            os.getenv("LECTURE_GENERATOR_ENDPOINT"),
            os.getenv("LECTURE_GENERATOR_ENDPOINT_ID"),
            os.getenv("LECTURE_GENERATOR_TOKEN")
        )
        video_id = caller.generate(
            {
                "topic": lecture_input.topic,
                "instructions": lecture_input.instructions,
                "language": "English",
                "ppt_base64": ppt_b64,
                "fps": 15,
                "voice": "onyx",
                "placeholders": content
            }
        ).get("response", {}).get("video_id")
        
        if not video_id:
            raise ValueError("Error generating presentation")
        
        video_bytes = redis_cache_manager.get(video_id)
        
        # Update the lecture with new data
        lecture_db.update_lecture(
            lecture_id,
            LectureUpdate(
                status=LectureStatus.READY,
                # Add any other fields you want to update
            ),
            video_file=BytesIO(video_bytes),
            ppt_file=BytesIO(open(file_path, "rb").read())
        )
        
    except Exception as e:
        logging.error(f"Error in background lecture creation: {e}")
        lecture_db.update_lecture(
            lecture_id,
            LectureUpdate(status=LectureStatus.FAILED)
        )

@router.post("/")
@require_points_for_feature("LECTURE", "LECTURE")
def make_lecture(
    lecture_input: MakeLectureInput,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    # Create a pending lecture
    if subscription_manager.get_subscription_type(user_id) in {SubscriptionType.FREE}:
        raise HTTPException(status_code=400, detail="You must be subscribed to use this feature.")
    
    lecture_id = lecture_db.create_lecture(
        LectureCreate(user_id=user_id, topic=lecture_input.topic, instructions=lecture_input.instructions),
        BytesIO(b""),
        BytesIO(b"")
    )

    model_name, premium_model = can_use_premium_model(user_id)
    ppt_pages = subscription_manager.get_feature_value(user_id, "ppt_pages").main_data if subscription_manager.get_feature_value(user_id, "ppt_pages") else 12

    # Add the main process to background tasks
    background_tasks.add_task(
        background_lecture_creation,
        lecture_id,
        user_id,
        lecture_input,
        model_name,
        premium_model,
        ppt_pages
    )

    return {"message": "Lecture creation started", "lecture_id": lecture_id}

@router.get("/user_lectures", response_model=List[LectureResponse])
def get_user_lectures(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    """
    Retrieve all lectures for the authenticated user.
    """
    try:
        lectures = lecture_db.get_user_lectures(user_id)
        return lectures
    except Exception as e:
        logging.error(f"Error retrieving lectures for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while retrieving lectures")

@router.get("/{lecture_id}", response_model=LectureResponse)
def get_lecture(
    lecture_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    """
    Retrieve a specific lecture by its ID.
    """
    try:
        lecture = lecture_db.get_lecture(lecture_id)
        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")
        if lecture.user_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this lecture")
        return lecture
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Error retrieving lecture {lecture_id} for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while retrieving the lecture")


@router.get("/{lecture_id}/video")
def download_lecture_video(
    lecture_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    """
    Download the video file for a specific lecture.
    """
    try:
        lecture = lecture_db.get_lecture(lecture_id)
        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")
        if lecture.user_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this lecture")
        
        video_data = lecture_db.download_video(lecture_id)
        if not video_data:
            raise HTTPException(status_code=404, detail="Video file not found")
        
        return Response(content=video_data, media_type="video/mp4")
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Error downloading video for lecture {lecture_id}, user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while downloading the video")

@router.get("/{lecture_id}/ppt")
def download_lecture_ppt(
    lecture_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    """
    Download the PPT file for a specific lecture.
    """
    try:
        lecture = lecture_db.get_lecture(lecture_id)
        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")
        if lecture.user_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this lecture")
        
        ppt_data = lecture_db.download_ppt(lecture_id)
        if not ppt_data:
            raise HTTPException(status_code=404, detail="PPT file not found")
        
        return Response(content=ppt_data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Error downloading PPT for lecture {lecture_id}, user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while downloading the PPT")
    
@router.delete("/{lecture_id}")
def delete_lecture(
    lecture_id: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: bool = Depends(verify_play_integrity),
):
    """
    Delete a specific lecture by its ID.
    """
    try:
        # First, retrieve the lecture to check ownership
        lecture = lecture_db.get_lecture(lecture_id)
        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")
        
        # Check if the authenticated user owns this lecture
        if lecture.user_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this lecture")
        
        # If checks pass, proceed with deletion
        success = lecture_db.delete_lecture(lecture_id)
        
        if success:
            return Response(status_code=204)  # 204 No Content for successful deletion
        else:
            raise HTTPException(status_code=500, detail="Failed to delete the lecture")
    
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Error deleting lecture {lecture_id} for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while deleting the lecture")
