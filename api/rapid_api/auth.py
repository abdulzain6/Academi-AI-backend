from fastapi import HTTPException, Request
from ..globals import RAPID_API_PROXY_SECRET, RAPID_API_PROXY_SECRET_WHISPER


def verify_rapidapi_key(request: Request):
    try:
        if request.headers.get("X-RapidAPI-Proxy-Secret") == RAPID_API_PROXY_SECRET:
            return
        else:
            raise ValueError("Invalid RapidAPI Proxy Secret")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    
def verify_rapidapi_key_whisper(request: Request):
    try:
        if request.headers.get("X-RapidAPI-Proxy-Secret") == RAPID_API_PROXY_SECRET_WHISPER:
            return
        else:
            raise ValueError("Invalid RapidAPI Proxy Secret")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e