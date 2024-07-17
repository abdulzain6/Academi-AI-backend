from fastapi import HTTPException, Request
from ..globals import RAPID_API_PROXY_SECRET


def verify_rapidapi_key(request: Request):
    try:
        if request.headers.get("X-RapidAPI-Proxy-Secret") == RAPID_API_PROXY_SECRET:
            return
        else:
            raise ValueError("Invalid RapidAPI Proxy Secret")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e