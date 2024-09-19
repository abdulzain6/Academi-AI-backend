import json
import os
import time
import uuid
import requests
import logging
import uuid
import yt_dlp

from ..globals import CACHE_DOCUMENT_URL_TEMPLATE, redis_cache_manager
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from langchain_community.document_loaders import YoutubeLoader

MAX_FILE_SIZE_MB = 1024
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

router = APIRouter()

class FileLinkRequest(BaseModel):
    file_link: str

class YoutubeLinkRequest(BaseModel):
    youtube_link: str

class YoutubeTranscriptResponse(BaseModel):
    transcript: str
    link: str


def is_youtube_video(url: str) -> bool:
    try:
        YoutubeLoader.extract_video_id(url)
        return True
    except Exception as e:
        return False

def download_audio_from_youtube(video_url: str) -> str:
    file_path = f"/tmp/{str(uuid.uuid4())}.m4a"  # Use .m4a for audio format
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]',  # Select the best audio format available (m4a in this case)
        'outtmpl': file_path,  # Save the file with the generated random ID
        'max_filesize': 200000000,  # Optional: Limit the maximum file size to 200 MB
        'concurrent_fragment_downloads': 8
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    return file_path



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


@router.post("/load-youtube-link", description="""Used to extract transcript of a youtube video""")
def load_file(
    request: YoutubeLinkRequest
):
    if not is_youtube_video(request.youtube_link):
        raise HTTPException(status_code=400, detail="Invalid link, The link is not of a youtube video")
        
    loader = YoutubeLoader.from_youtube_url(
        request.youtube_link,
        language=[
            "en",
            "es",
            "zh",
            "hi",
            "ar",
            "bn",
            "pt",
            "ru",
            "ja",
            "de",
            "jv",
            "ko",
            "fr",
            "tr",
            "mr",
            "vi",
            "ta",
            "ur",
            "it",
            "th",
            "gu",
            "pl",
            "uk",
            "ro",
            "nl",
            "hu",
            "el",
            "sv",
            "da",
            "fi",
        ],
    )

    docs = loader.load()
    contents = " ".join([doc.page_content for doc in docs])
    
    if not contents or "YouTubeAboutPressCopyrightContact" in contents:
        file_path = download_audio_from_youtube(request.youtube_link)
        with open(file_path, "rb") as fp:
            redis_cache_manager.set(key=file_path, value=fp.read(), ttl=18000, suppress=False)
            document_url = CACHE_DOCUMENT_URL_TEMPLATE.format(doc_id=file_path)
            headers = {
                'Authorization': f'Bearer {os.getenv("RUNPOD_API_KEY")}',
                'Content-Type': 'application/json',
            }
            
            json_data = {
                'input': {
                    'audio': document_url,
                    'model': 'base',
                    'transcription': 'plain_text'
                },
            }
    
            # Make the request to Runpod API
            try:
                start = time.time()
                response = requests.post(os.getenv('RUNPOD_WHISPER_ENDPOINT'), headers=headers, json=json_data)
                logging.info(f"Time taken for inference: {time.time() - start}")
                response.raise_for_status()
                contents = response.json().get("output")
            except Exception as e:
                logging.error(f"Error in whisper processing: {e}")
                try:
                    logging.error(f"Returned error response {response.text}, Error: {response.json()['error']}")
                    error = json.loads(response.json()['error'])
                    
                    logging.info(f"ERROR MESSAGE: {error} {type(error)}")
                    if 'No such file or' in error['error_message']:
                        error_message = "Invalid Link"
                    else:
                        error_message = error
                    return JSONResponse(status_code=400, content={"error" : error_message})
                except Exception as e:
                    logging.error(f"Error: {e}")
                raise HTTPException(500, f"Error in processing.")

    return YoutubeTranscriptResponse(transcript=contents, link=request.youtube_link)