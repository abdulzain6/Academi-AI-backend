import base64
import json
import os
import time
import uuid
import requests
import logging

from fastapi.encoders import jsonable_encoder
from .auth import verify_rapidapi_key
from ..globals import CACHE_DOCUMENT_URL_TEMPLATE, redis_cache_manager
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from enum import Enum

MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

router = APIRouter()


class WhisperModel(str, Enum):
    tiny = "tiny"
    base = "base"
    small = "small"
    medium = "medium"
    large_v3 = "large-v3"

class TranscriptionFormat(str, Enum):
    plain_text = "plain_text"
    formatted_text = "formatted_text"
    srt = "srt"
    vtt = "vtt"

class FasterWhisperRequest(BaseModel):
    audio: Optional[str] = Field(description="Url to the audio file")
    model: WhisperModel = Field(WhisperModel.base, description='Choose a Whisper model.')
    transcription: TranscriptionFormat = Field(TranscriptionFormat.plain_text, description='Choose the format for the transcription.')
    translate: bool = Field(False, description="Translate the text to English when set to True")
    language: Optional[str] = Field(None, description="Language spoken in the audio, specify None to perform language detection")
    temperature: float = Field(0, description="Temperature to use for sampling")
    best_of: int = Field(5, description="Number of candidates when sampling with non-zero temperature")
    beam_size: int = Field(5, description="Number of beams in beam search, only applicable when temperature is zero")
    patience: Optional[float] = Field(None, description="Optional patience value to use in beam decoding")
    length_penalty: Optional[float] = Field(None, description="Optional token length penalty coefficient (alpha)")
    suppress_tokens: str = Field("-1", description="Comma-separated list of token ids to suppress during sampling")
    initial_prompt: Optional[str] = Field(None, description="Optional text to provide as a prompt for the first window")
    condition_on_previous_text: bool = Field(True, description="If True, provide the previous output of the model as a prompt for the next window")
    temperature_increment_on_fallback: float = Field(0.2, description="Temperature to increase when falling back when the decoding fails")
    compression_ratio_threshold: float = Field(2.4, description="If the gzip compression ratio is higher than this value, treat the decoding as failed")
    logprob_threshold: float = Field(-1.0, description="If the average log probability is lower than this value, treat the decoding as failed")
    no_speech_threshold: float = Field(0.6, description="If the probability of the token is higher than this value, consider the segment as silence")
    enable_vad: bool = Field(False, description="If True, use the voice activity detection (VAD) to filter out parts of the audio without speech. This step is using the Silero VAD model")
    word_timestamps: bool = Field(False, description="If True, include word timestamps in the output")

    @model_validator(mode='before')
    def check_audio_fields(cls, values):
        audio, audio_base64 = values.get('audio'), values.get('audio_base64')
        if not audio and not audio_base64:
            raise ValueError('Either audio or audio_base64 must be provided')
        return values
    

ALLOWED_MODELS = {
    "BASIC" : [WhisperModel.tiny, WhisperModel.base, WhisperModel.small],
    "PRO" : [WhisperModel.tiny, WhisperModel.base, WhisperModel.small, WhisperModel.medium],
    "ULTRA" : [WhisperModel.tiny, WhisperModel.base, WhisperModel.small, WhisperModel.medium],
    "MEGA" : [WhisperModel.tiny, WhisperModel.base, WhisperModel.small, WhisperModel.medium, WhisperModel.large_v3]
}

def get_subscription_tier(request: Request):
    tier = request.headers.get("X-RapidAPI-Subscription-Tier")
    if not tier:
        raise HTTPException(status_code=403, detail="RapidAPI subscription tier not found")
    return tier

@router.post("/faster_whisper/", description="""Used to process audio using faster whisper.
Takes in an audio link and configuration and returns the transcript.""")
def process_audio(
    request: FasterWhisperRequest,
    plan: str = Depends(get_subscription_tier),
    rapid_key = Depends(verify_rapidapi_key)
):
    logging.info(f"Recieved request for faster whisper. {request.model_dump()} Plan {plan}")
    
    allowed_models = ALLOWED_MODELS.get(plan)
    if not allowed_models:
        return JSONResponse(status_code=400, content={"error": f"Invalid plan: {plan}"})

    if request.model not in allowed_models:
        request.model = allowed_models[-1]
    
    
    headers = {
        'Authorization': f'Bearer {os.getenv("RUNPOD_API_KEY")}',
        'Content-Type': 'application/json',
    }

    json_data = {
        'input': jsonable_encoder(request.model_dump(exclude_none=True)),
    }
    try:
        start = time.time()
        response = requests.post(os.getenv('RUNPOD_WHISPER_ENDPOINT'), headers=headers, json=json_data)
        logging.info(f"Time taken for inference: {time.time() - start}")
        response.raise_for_status()
        output = response.json()["output"]
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
            return JSONResponse(status_code=500, content={"error" : error_message})
        except Exception as e:
            logging.error(f"Error: {e}")
            
        raise HTTPException(500, f"Error in processing. Please check your link and configuration params")

    return {"message": "Processing complete", "output": output}


@router.post("/faster_whisper-simple/", description="""Used to process audio using faster whisper.
Takes in an audio file and returns the transcript.""")
def process_audio(
    file: UploadFile = File(...),
    rapid_key = Depends(verify_rapidapi_key),
    plan: str = Depends(get_subscription_tier),
):
    logging.info(f"Recieved request for faster whisper simple Plan {plan}")
    
    try:
        content = file.file.read()
    except Exception as e:
        logging.error(f"Error reading file: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")
    
    if file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds 200 MB limit")
    
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
        output = response.json().get("output")
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
            return JSONResponse(status_code=500, content={"error" : error_message})
        except Exception as e:
            logging.error(f"Error: {e}")
        raise HTTPException(500, f"Error in processing.")
    
    return {"message": "Processing complete", "output": output}