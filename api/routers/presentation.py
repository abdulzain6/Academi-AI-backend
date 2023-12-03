import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import Depends, HTTPException
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    collection_manager,
    file_manager,
    template_manager,
    temp_knowledge_manager,
    knowledge_manager,
    subscription_manager
)
from ..lib.presentation_maker.presentation_maker import PresentationInput, PresentationMaker, PexelsImageSearch
from ..dependencies import get_model, require_points_for_feature, use_feature_with_premium_model_check
from langchain.chat_models import ChatOpenAI
from pydantic import BaseModel


class GetTemplateResponse(BaseModel):
    templates: list[dict[str, str]]
    images: list[dict[str, str]]


class MakePresentationInput(PresentationInput):
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


@router.post("/")
@require_points_for_feature("PRESENTATION", "PRESENTATION")
def make_presentation(
    presentation_input: MakePresentationInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    model_name, premium_model = use_feature_with_premium_model_check("PRESENTATION", user_id=user_id)
    llm = get_model({"temperature": 0.3}, False, premium_model, cache=False)        
    ppt_pages = subscription_manager.get_feature_value(user_id, "ppt_pages").main_data or 12
    ppt_pages = max(ppt_pages, 4)
    presentation_input.number_of_pages = min(presentation_input.number_of_pages, ppt_pages)
    
    logging.info(f"Using model {model_name} to make presentation for user {user_id}")
    presentation_maker = PresentationMaker(
        template_manager,
        temp_knowledge_manager,
        llm,
        pexel_image_gen_cls=PexelsImageSearch,
        image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
        vectorstore=knowledge_manager,
    )
    
    logging.info(f"Got ppt generation request, {user_id}... Input: {presentation_input}")

    if presentation_input.use_data:
        if presentation_input.collection_name:
            if collection := collection_manager.get_collection_by_name_and_user(
                presentation_input.collection_name, user_id
            ):
                vectordb_collection = collection.vectordb_collection_name
            else:
                logging.error(f"Collection does not exist, {user_id}")
                raise HTTPException(400, "Collection does not exist.")

            if presentation_input.files and not verify_file_existance(
                user_id, presentation_input.files, collection.collection_uid
            ):
                logging.error(f"files does not exist, {user_id}")
                raise HTTPException(400, "Some files dont exist")

    else:
        vectordb_collection = None

    if not presentation_input.auto_select_template:
        template_name = presentation_input.template_name
    else:
        template_name = None

    try:
        file_path = presentation_maker.make_presentation(
            PresentationInput(
                topic=presentation_input.topic,
                instructions=presentation_input.instructions,
                number_of_pages=presentation_input.number_of_pages,
                negative_prompt=presentation_input.negative_prompt,
                collection_name=vectordb_collection,
                files=presentation_input.files,
            ),
            template_name,
        )
    except Exception as e:
        logging.error(f"Error in making ppt, Error: {e}  User: {user_id}")
        raise HTTPException(400, str(e)) from e

    logging.info(f"Presentation made successfully! {user_id}")
        
    return FileResponse(
        file_path,
        headers={
            "Content-Disposition": f"attachment; filename={file_path.split('/')[-1]}"
        },
    )
