import contextlib
from io import BytesIO
import logging
import os
from typing import Optional
from urllib.parse import quote
from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import Depends, HTTPException

from api.lib.diagram_maker import DiagramMaker
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    collection_manager,
    file_manager,
    template_manager,
    temp_knowledge_manager,
    knowledge_manager,
    subscription_manager,
    presentation_db
)
from ..lib.presentation_maker.presentation_maker import PresentationInput, PresentationMaker, PexelsImageSearch
from ..dependencies import get_model, require_points_for_feature, use_feature_with_premium_model_check
from pydantic import BaseModel
from api.lib.database.presentation import Presentation
from ..lib.utils import convert_first_slide_to_image


class GetTemplateResponse(BaseModel):
    templates: list[dict[str, str]]
    images: list[dict[str, str]]

class MakePresentationInput(BaseModel):
    topic: str
    instructions: str
    number_of_pages: int
    negative_prompt: str
    collection_name: Optional[str]
    files: Optional[list[str]]
    use_data: bool = True
    auto_select_template: bool = True
    template_name: Optional[str] = ""


def verify_file_existance(
    user_id: str, file_names: list[str], collection_uid: str
) -> bool:
    return all(
        file_manager.file_exists(user_id, collection_uid, file_name)
        for file_name in file_names
    )


router = APIRouter()


@router.get("/templates", response_model=GetTemplateResponse)
def get_available_templates(
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
) -> GetTemplateResponse:
    logging.info(f"Got get ppt templates request, {user_id}")

    templates = template_manager.get_all_templates()

    formatted_templates = [
        {template.template_name.title(): template.template_description}
        for template in templates
    ]
    images = [
        {template.template_name.title(): template.image_base64}
        for template in templates
    ]
    logging.info(f"processed get ppt templates request, {user_id}")
    return GetTemplateResponse(templates=formatted_templates, images=images)

@router.delete("/{presentation_id}")
def delete_presentation(
    presentation_id: str,
    user_id: str = Depends(get_user_id)
):
    """Delete a specific presentation by presentation_id for the current user."""
    try:
        # Ensure the presentation_id is a valid ObjectId
        presentation_id = ObjectId(presentation_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid presentation ID.")
    
    deleted = presentation_db.delete_presentation(user_id=user_id, presentation_id=presentation_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Presentation not found or does not belong to this user.")
    
    return {"message": "Presentation deleted successfully."}

@router.get("/{presentation_id}")
def get_presentation_by_id(
    presentation_id: str,
    user_id: str = Depends(get_user_id)
) -> Optional[dict]:
    """Retrieve a specific presentation by presentation_id for the current user."""
    try:
        # Ensure the presentation_id is a valid ObjectId
        presentation_id = ObjectId(presentation_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid presentation ID.")

    presentation = presentation_db.get_presentation(user_id=user_id, presentation_id=presentation_id)

    if not presentation:
        raise HTTPException(status_code=404, detail="Presentation not found or does not belong to this user.")

    return presentation

@router.get("/")
def get_all_presentations_for_user(user_id: str = Depends(get_user_id)) -> list[dict]:
    """Retrieve all presentations for a given user."""
    presentation_list = presentation_db.get_presentations_by_user(user_id)
    if not presentation_list:
        raise HTTPException(status_code=404, detail="No presentations found for this user.")
    
    return presentation_list

@router.post("/")
@require_points_for_feature("PRESENTATION", "PRESENTATION")
def make_presentation(
    presentation_input: MakePresentationInput,
    background_tasks: BackgroundTasks,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
 #   model_name, premium_model = use_feature_with_premium_model_check("PRESENTATION", user_id=user_id)
    llm = get_model({"temperature": 0}, False, False, cache=False, alt=True)
    if val := subscription_manager.get_feature_value(user_id, "ppt_pages"):   
        ppt_pages = val.main_data
    else:
        ppt_pages = 12
        
    ppt_pages = max(ppt_pages, 4)
    presentation_input.number_of_pages = min(presentation_input.number_of_pages, ppt_pages)
    
   # logging.info(f"Using model {model_name} to make presentation for user {user_id}")
    presentation_maker = PresentationMaker(
        template_manager,
        temp_knowledge_manager,
        llm,
        vectorstore=knowledge_manager,
        diagram_maker=DiagramMaker(None, llm, None)
    )
    
    logging.info(f"Got ppt generation request, {user_id}... Input: {presentation_input}")

    if presentation_input.use_data:
        if presentation_input.collection_name:
            if collection := collection_manager.get_collection_by_name_and_user(
                presentation_input.collection_name, user_id
            ):
                coll_name = collection.name
            else:
                logging.error(f"Collection does not exist, {user_id}")
                raise HTTPException(400, "Collection does not exist.")

            if presentation_input.files and not verify_file_existance(
                user_id, presentation_input.files, collection.collection_uid
            ):
                logging.error(f"files does not exist, {user_id}")
                raise HTTPException(400, "Some files dont exist")
        else:
            coll_name = None

    else:
        coll_name = None

    if not presentation_input.auto_select_template:
        template_name = presentation_input.template_name
    else:
        template_name = None

    try:
        file_path, content = presentation_maker.make_presentation(
            PresentationInput(
                topic=presentation_input.topic,
                instructions=presentation_input.instructions,
                number_of_pages=presentation_input.number_of_pages,
                negative_prompt=presentation_input.negative_prompt,
                collection_name=coll_name,
                files=presentation_input.files,
                user_id=user_id
            ),
            template_name,
        )
    except Exception as e:
        logging.error(f"Error in making ppt, Error: {e}  User: {user_id}")
        raise HTTPException(400, str(e)) from e

    logging.info(f"Presentation made successfully! {user_id}")

    try:
        store_presentation_task(
            user_id=user_id, 
            presentation_input=presentation_input, 
            file_path=file_path
        )
    except Exception as e:
        logging.error(f"Error in storing ppt, Error: {e}  User: {user_id}")

    return FileResponse(file_path, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_path.split('/')[-1], safe='')}"})


def store_presentation_task(user_id: str, presentation_input: MakePresentationInput, file_path: str):
    """Background task to store the presentation and thumbnail."""
    with open(file_path, "rb") as fp:
        presentation_db.store_presentation(
            user_id=user_id,
            presentation=Presentation(
                topic=presentation_input.topic,
                instructions=presentation_input.instructions,
                number_of_pages=presentation_input.number_of_pages
            ),
            thumbnail_file=convert_first_slide_to_image(file_path),
            pptx_file=BytesIO(fp.read())
        )
