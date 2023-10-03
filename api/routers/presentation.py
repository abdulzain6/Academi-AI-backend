from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import Depends, HTTPException, status
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    collection_manager,
    file_manager,
    presentation_maker,
    template_manager,
)
from ..lib.presentation_maker.presentation_maker import PresentationInput
from ..decorators import require_points_for_feature
from pydantic import BaseModel


class GetTemplateResponse(BaseModel):
    templates: list[dict[str, str]]


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
    templates = template_manager.get_all_templates()

    formatted_templates = [
        {template.template_name.title(): template.template_description}
        for template in templates
    ]

    return GetTemplateResponse(templates=formatted_templates)


@router.post("/")
def make_presentation(
    presentation_input: MakePresentationInput,
    user_id=Depends(get_user_id),
    _=Depends(require_points_for_feature("PRESENTATION")),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if presentation_input.use_data:
        if presentation_input.collection_name:
            if collection := collection_manager.get_collection_by_name_and_user(
                presentation_input.collection_name, user_id
            ):
                vectordb_collection = collection.vectordb_collection_name
            else:
                raise HTTPException(400, "Collection does not exist.")

            if presentation_input.files and not verify_file_existance(
                user_id, presentation_input.files, collection.collection_uid
            ):
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
        raise HTTPException(400, str(e)) from e

    return FileResponse(
        file_path,
        headers={
            "Content-Disposition": f"attachment; filename={file_path.split('/')[-1]}"
        },
    )
