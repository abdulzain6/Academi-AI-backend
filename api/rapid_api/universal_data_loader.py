import json
import os
import time
import uuid
import requests
import logging

from ..globals import CACHE_DOCUMENT_URL_TEMPLATE, redis_cache_manager
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MAX_FILE_SIZE_MB = 1024
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

router = APIRouter()

class FileLinkRequest(BaseModel):
    file_link: str



@router.post("/load-file", description="""Used to extract text and metadata from documents of
anytype. Including docx, pdf, pptx, epub, html and many more.""")
def load_file(
    file: UploadFile = File(...)
):
    logging.info(f"Recieved request for universal data loader (file)")
    
    try:
        content = file.file.read()
    except Exception as e:
        logging.error(f"Error reading file: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")
    
    if file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds 1024 MB limit")
    
    filename = file.filename
    _, file_extension = os.path.splitext(filename)    
    
    doc_id = f"{uuid.uuid4()}{file_extension}"
    redis_cache_manager.set(key=doc_id, value=content, ttl=18000, suppress=False)
    document_url = CACHE_DOCUMENT_URL_TEMPLATE.format(doc_id=doc_id)
    logging.info("File upload complete")
    
    headers = {
        'Authorization': f'Bearer {os.getenv("RUNPOD_API_KEY")}',
        'Content-Type': 'application/json',
    }
    
    json_data = {
        'input': {
            'file_link': document_url,
            'mode': 'paged',
        },
    }
    
    try:
        start = time.time()
        response = requests.post(os.getenv('RUNPOD_EXTRACTOR_ENDPOINT'), headers=headers, json=json_data)
        logging.info(f"Time taken for inference: {time.time() - start}")
        response.raise_for_status()
        output = response.json()["output"]
    except Exception as e:
        logging.error(f"Error in extractor processing: {e}")
        try:
            logging.error(f"Returned error response {response.text}, Error: {response.json()['error']}")
            error = json.loads(response.json()['error'])["error_message"]
            logging.info(f"ERROR MESSAGE: {error} {type(error)}")
            return JSONResponse(status_code=500, content={"error" : error})
        except Exception as e:
            logging.error(f"Error: {e}")
            
        raise HTTPException(500, f"Error in processing. Please check your link and configuration params")

    return {"message": "Processing complete", "output": output}


@router.post("/load-file-link", description="""Used to extract text and metadata from documents of
anytype. Including docx, pdf, pptx, epub, html and many more.""")
def load_file(
    request: FileLinkRequest
):
    file_link = request.file_link
    
    logging.info(f"Recieved request for universal data loader (file) Link: {file_link}")
    headers = {
        'Authorization': f'Bearer {os.getenv("RUNPOD_API_KEY")}',
        'Content-Type': 'application/json',
    }
    json_data = {
        'input': {
            'file_link': file_link,
            'mode': 'paged',
        },
    }
    try:
        start = time.time()
        response = requests.post(os.getenv('RUNPOD_EXTRACTOR_ENDPOINT'), headers=headers, json=json_data)
        logging.info(f"Time taken for inference: {time.time() - start}")
        response.raise_for_status()
        output = response.json()["output"]
    except Exception as e:
        logging.error(f"Error in extractor processing: {e}")
        try:
            logging.error(f"Returned error response {response.text}, Error: {response.json()['error']}")
            error = json.loads(response.json()['error'])["error_message"]
            logging.info(f"ERROR MESSAGE: {error} {type(error)}")
            return JSONResponse(status_code=500, content={"error" : error})
        except Exception as e:
            logging.error(f"Error: {e}")
            
        raise HTTPException(500, f"Error in processing. Please check your link and configuration params")

    
    return {"message": "Processing complete", "output": output}