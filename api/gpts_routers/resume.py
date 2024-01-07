import base64
import logging
import os
import random
import shutil
import tempfile
import uuid
import img2pdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from api.lib.cv_maker.cv_maker import CVMaker
from api.lib.cv_maker.template_loader import template_loader
from langchain.chat_models import ChatOpenAI
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.config import GPT_API_KEY
from api.globals import knowledge_manager, redis_cache_manager, CACHE_DOCUMENT_URL_TEMPLATE
from enum import Enum

router = APIRouter()

security = HTTPBearer()



def image_to_pdf_in_memory(image_path: str) -> bytes:
    """
    Convert an image to a PDF and return it as an in-memory bytes object using img2pdf.

    Args:
    image_path (str): The path to the input image file.

    Returns:
    bytes: The PDF file as a bytes object.
    """
    with open(image_path, "rb") as img_file:
        pdf_bytes = img2pdf.convert(img_file)

    return pdf_bytes

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if credentials.credentials == GPT_API_KEY:
        return 
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_cv_templates():
    cv_maker = CVMaker(
        templates=template_loader(),
        chrome_path="/usr/bin/google-chrome",
        chat_model=ChatOpenAI(temperature=0)

    )
    return {"templates" : cv_maker.get_all_templates()}

class OutputFormat(Enum):
    PDF = "PDF"
    IMAGE = "IMAGE"

class MakeCV(BaseModel):
    input_dict: dict = Field(json_schema_extra={"description" : "The json which follows the correct schema for the template provided by get_cv_templates. Ask user for missing values"})
    template_name: str = Field(json_schema_extra={"description" : f"The name of the template to use. Must be from {list(get_cv_templates().keys())}"})
    output_format: OutputFormat = Field(OutputFormat.PDF, json_schema_extra={"description" : "The format to output the resume in, can be 'PDF' OR 'IMAGE'"})





@router.get("/get_cv_templates", description="""
Used to get Available Resume Templates and schema of json that can be used to fill them using make_cv.
""")
def get_templates(_ = Depends(verify_token)):
    return get_cv_templates()

@router.post("/make_cv", description="Used to create a cv. It takes in a template name and the json that follows proper schema. Ask user for missing values")
def make_cv(cv_input: MakeCV, _ = Depends(verify_token)):
    cv_maker = CVMaker(
        templates=template_loader(),
        chrome_path="/usr/bin/google-chrome",
        chat_model=ChatOpenAI(temperature=0, model="gpt-3.5-turbo-1106").bind(response_format = {"type": "json_object"})
    )

    if not cv_maker.get_template_by_name(cv_input.template_name):
        raise HTTPException(400, detail="CV Template does not exist")

    with tempfile.NamedTemporaryFile(delete=True, suffix=".png", mode='w+b') as tmp_file:
        tmp_file_path = tmp_file.name
        output_file_name = os.path.basename(tmp_file_path)
        output_file_directory = os.path.dirname(tmp_file_path)
    
        if cv_input.input_dict:
            try:
                cv_maker.make_cv(cv_input.template_name, cv_input.input_dict, output_file_path=output_file_directory, output_file_name=output_file_name)
            except Exception as e:
                raise HTTPException(400, detail=str(e))
            
        rand_id = str(uuid.uuid4())
        if cv_input.output_format == OutputFormat.IMAGE:
            with open(tmp_file_path, "rb") as img_file:
                image_bytes = img_file.read()
            redis_cache_manager.set(key=rand_id, value=image_bytes, ttl=18000, suppress=False)
            document_url = CACHE_DOCUMENT_URL_TEMPLATE.format(doc_id=rand_id)
            return f"CV Available at: {document_url}. Give the following link as it is to the user dont add sandbox prefix to it {document_url}. "
        else:
            pdf_bytes = image_to_pdf_in_memory(tmp_file_path)
            redis_cache_manager.set(key=rand_id, value=pdf_bytes, ttl=18000, suppress=False)
            document_url = CACHE_DOCUMENT_URL_TEMPLATE.format(doc_id=rand_id)
            return f"CV Available at: {document_url}. Give the following link as it is to the user dont add sandbox prefix to it {document_url}. "

@router.post("/extract-text/", description="Used to extract text from any file. You can use this to take an existing cv and tailor it to a new job description")
def extract_text_from_pdf(file: UploadFile = File(...), _ = Depends(verify_token)):
    try:
        file_extension = os.path.splitext(file.filename)[1]
    except Exception:
        raise HTTPException(400, "File doesnt have an extension. It must have one")
    
    temp_file_path = f"temp_{random.randrange(1, 1000000)}{file_extension}"    
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            buffer.seek(0)  # Reset the file pointer to the beginning
        try:
            docs = knowledge_manager.load_using_unstructured(
                temp_file_path
            )
            extracted_text = "\n".join([doc.page_content for doc in docs])
        except Exception as e:
            import traceback
            logging.error(f"File not supported, Error: {traceback.format_exception(e)}")
            raise HTTPException(400, "FIle not supported/ FIle has no Data, Handwritten text not supported if provided.") from e

        return JSONResponse(content={"text": extracted_text or "No text found."})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)