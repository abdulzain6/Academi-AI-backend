import base64
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..globals import subscription_manager, temp_knowledge_manager, template_manager, knowledge_manager, collection_manager, file_manager
from ..auth import get_user_id, verify_play_integrity
from ..lib.presentation_maker.presentation_maker import PresentationInput, PresentationMaker, PexelsImageSearch
from ..dependencies import get_model, can_use_premium_model
from ..lib.runpod_caller import RunpodCaller



router = APIRouter()

class MakePresentationInput(BaseModel):
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
    
@router.post("/")
#@require_points_for_feature("PRESENTATION", "PRESENTATION")
def make_lecture(
    presentation_input: MakePresentationInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    model_name, premium_model = can_use_premium_model(user_id)
    llm = get_model({"temperature": 0}, False, True, premium_model, cache=False)
    if val := subscription_manager.get_feature_value(user_id, "ppt_pages"):   
        ppt_pages = val.main_data
    else:
        ppt_pages = 12
        
    
    logging.info(f"Using model {model_name} to make presentation for user {user_id}")
    presentation_maker = PresentationMaker(
        template_manager,
        temp_knowledge_manager,
        llm,
        pexel_image_gen_cls=PexelsImageSearch,
        image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
        vectorstore=knowledge_manager,
    )
    
    logging.info(f"Got lecture generation request, {user_id}... Input: {presentation_input}")

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

    try:
        file_path, content = presentation_maker.make_presentation(
            PresentationInput(
                topic=presentation_input.topic,
                instructions=presentation_input.instructions,
                number_of_pages=ppt_pages,
                negative_prompt=presentation_input.negative_prompt,
                collection_name=coll_name,
                files=presentation_input.files,
                user_id=user_id
            ),
            None,
        )
    except Exception as e:
        logging.error(f"Error in making ppt, Error: {e}  User: {user_id}")
        raise HTTPException(400, str(e)) from e

    logging.info(f"Presentation made successfully! {user_id}")
    logging.info(f"Presentation path: {file_path}")
    
    with open(file_path, "rb") as file:
        ppt_b64 = base64.b64encode(file.read()).decode("utf-8")
    
    caller = RunpodCaller(
        "https://api.runpod.ai/v2/pjl4tkbjipn1nq/runsync",
        "pjl4tkbjipn1nq",
        "7SB05Z7GVUU46HNLWZ3KDJWJT6XIIHJ5H4B96U85"
    )
    print(caller.generate(
        {
            "topic" : presentation_input.topic,
            "instructions" : presentation_input.instructions,
            "language" : "English",
            "ppt_base64" : ppt_b64,
            "fps" : 15,
            "voice" : "onyx",
            "placeholders" : content
        }
    ))
    