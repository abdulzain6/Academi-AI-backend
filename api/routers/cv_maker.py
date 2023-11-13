import os
import tempfile
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from ..auth import get_user_id, verify_play_integrity
from ..globals import get_model
from pydantic import BaseModel
from typing import Optional
from ..lib.cv_maker.cv_maker import CVMaker
from ..lib.cv_maker.template_loader import template_loader
import logging


router = APIRouter()

class MakeCV(BaseModel):
    input_dict: Optional[dict] = None
    template_name: str
    data_str: Optional[str] = None
    

def delete_temp_file(path: str):
    try:
        os.remove(path)
    except Exception as e:
        print(f"Error deleting file: {e}")

@router.get("/get_cv_templates")
def get_cv_templates(
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    cv_maker = CVMaker(
        templates=template_loader(),
        chrome_path="/usr/bin/google-chrome",
        chat_model=get_model({"temperature" : 0}, stream=False, is_premium=False)
    )
    logging.info(f"Getting all CV templates for {user_id}")
    return {"templates" : cv_maker.get_all_templates()}
    
    
@router.post("/make_cv")
def make_cv(
    background_tasks: BackgroundTasks,
    cv_input: MakeCV,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if not cv_input.data_str and not cv_input.input_dict:
        raise HTTPException(400, detail="Input dictionary or data string must be provided")
    
    cv_maker = CVMaker(
        templates=template_loader(),
        chrome_path="/usr/bin/google-chrome",
        chat_model=get_model({"temperature" : 0.2}, stream=False, is_premium=False)
    )
    if not cv_maker.get_template_by_name(cv_input.template_name):
        raise HTTPException(400, detail="CV Template does not exist")
    

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='w+b') as tmp_file:
        tmp_file_path = tmp_file.name
        output_file_name = os.path.basename(tmp_file_path)
        output_file_directory = os.path.dirname(tmp_file_path)
        
    if cv_input.input_dict:
        cv_maker.make_cv(cv_input.template_name, cv_input.input_dict, output_file_path=output_file_directory, output_file_name=output_file_name)
    else:
        cv_maker.make_cv_from_string(cv_input.template_name, cv_input.data_str, output_file_path=output_file_directory, output_file_name=output_file_name)

    background_tasks.add_task(delete_temp_file, tmp_file_path)
    return FileResponse(tmp_file_path, filename=output_file_name, media_type="image/png")
