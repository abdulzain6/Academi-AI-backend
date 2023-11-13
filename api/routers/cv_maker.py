import base64
import os
import tempfile
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..auth import get_user_id, verify_play_integrity
from ..globals import get_model
from ..lib.cv_maker.cv_maker import CVMaker
from ..lib.cv_maker.template_loader import template_loader
from .utils import image_to_pdf_in_memory, file_to_base64


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
        chat_model=get_model({"temperature": 0.2}, stream=False, is_premium=False)
    )

    if not cv_maker.get_template_by_name(cv_input.template_name):
        raise HTTPException(400, detail="CV Template does not exist")

    with tempfile.NamedTemporaryFile(delete=True, suffix=".png", mode='w+b') as tmp_file:
        try:
            tmp_file_path = tmp_file.name
            output_file_name = os.path.basename(tmp_file_path)
            output_file_directory = os.path.dirname(tmp_file_path)
        
            if cv_input.input_dict:
                cv_maker.make_cv(cv_input.template_name, cv_input.input_dict, output_file_path=output_file_directory, output_file_name=output_file_name)
            else:
                cv_maker.make_cv_from_string(cv_input.template_name, cv_input.data_str, output_file_path=output_file_directory, output_file_name=output_file_name)
            
            print("convertinf")
            pdf_bytes = image_to_pdf_in_memory(tmp_file_path)
            print("converted")
            pdf_base64 = base64.b64encode(pdf_bytes).decode()

            with open(tmp_file_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode()

            return {"pdf": pdf_base64, "image": image_base64}
        finally:
            background_tasks.add_task(delete_temp_file, tmp_file_path)