from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from fastapi import Depends, HTTPException, Header, status
from firebase_admin import app_check
from google.oauth2 import id_token
from google.auth.transport import requests
from google.oauth2 import service_account
from .globals import credentials_path, redis_cache_manager
from .firebase import default_app
from .config import API_KEY_BACKDOOR, CRONJOB_KEY

import logging
import jwt


security = HTTPBearer()

def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    cache_key = f"token:{token}"
    try:
        return get_set_user_id(cache_key, token)
    except Exception as e:
        redis_cache_manager.delete(cache_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_set_user_id(cache_key, token):
    if cached_user_id := redis_cache_manager.get(cache_key):
        logging.info("Returning cached user ID...")
        return cached_user_id

    user = auth.verify_id_token(token, app=default_app)
    user_id = user["user_id"]
    logging.info("Verified token, storing in cache...")
    redis_cache_manager.set(cache_key, user_id)
    return user_id

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    cache_key = f"user_details:{token}"

    if cached_user := redis_cache_manager.get(cache_key):
        return cached_user

    try:
        user = auth.verify_id_token(token, app=default_app)
        user_details = auth.get_user(user["user_id"])
        user_data = {
            "email": user_details.email,
            "user_id": user["user_id"],
            "display_name": user_details.display_name,
            "photo_url": user_details.photo_url,
        }

        redis_cache_manager.set(cache_key, user_data)
        return user_data
    except Exception as e:
        logging.error(f"Error in id token. {e}")
        redis_cache_manager.delete(cache_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
        

def verify_play_integrity(x_firebase_appcheck: str = Header(...)) -> None:
    cache_key = f"app_check:{x_firebase_appcheck}"
    if x_firebase_appcheck == API_KEY_BACKDOOR:
        return
    
    # Check if we have a cached result for this token
    if cached_result := redis_cache_manager.get(cache_key):
        if cached_result == "valid":
            return
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Play Integrity token",
            )

    try:
        app_check_claims = app_check.verify_token(x_firebase_appcheck)
        # Token is valid, cache this result
        redis_cache_manager.set(cache_key, "valid", ttl=3600)  # expire after 1 hour
    except (ValueError, jwt.exceptions.DecodeError) as e:
        # Token is invalid, cache this result as well but with a shorter expiration time
        redis_cache_manager.set(cache_key, "invalid", ttl=300)  # expire after 5 minutes
        logging.error(f"Error in app check token. {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Play Integrity token, switch to latest version",
        ) from e
        
def verify_google_token(id_token_header: HTTPAuthorizationCredentials = Depends(security)):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=["https://www.googleapis.com/auth/androidpublisher"]
        )
        request = requests.Request()
        credentials.refresh(request)
        return id_token.verify_oauth2_token(
            id_token_header.credentials, request, audience="https://api.academiai.org/api/v1/subscriptions/playstore/rtdn"
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    
def verify_cronjob_request(id_token_header: HTTPAuthorizationCredentials = Depends(security)):
    try:
        if id_token_header.credentials == CRONJOB_KEY:
            return
        else:
            raise ValueError("Wrong key")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e