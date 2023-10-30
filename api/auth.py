from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from fastapi import Depends, HTTPException, Header, status
from firebase_admin import app_check
from google.oauth2 import id_token
from google.auth.transport import requests
from google.oauth2 import service_account
from .globals import credentials_path
from .firebase import default_app

import logging
import jwt


security = HTTPBearer()

def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        token = credentials.credentials
        logging.info(f"Verifying token..... {token}")
        user = auth.verify_id_token(token, app=default_app)
        logging.info("Verified token.....")
        return user["user_id"]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        user = auth.verify_id_token(token, app=default_app)
        user_details = auth.get_user(user["user_id"])
        return {
            "email": user_details.email,
            "user_id": user["user_id"],
            "display_name": user_details.display_name,
            "photo_url": user_details.photo_url,
        }
    except Exception as e:
        logging.error(f"Error in id token. {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
        
def verify_play_integrity(x_firebase_appcheck: str = Header(...)) -> None:
    try:
        return
        app_check_claims = app_check.verify_token(x_firebase_appcheck)
    except (ValueError, jwt.exceptions.DecodeError) as e:
        logging.error(f"Error in app check token. {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Play Integrity token",
        ) from e
        
def verify_google_token(id_token_header: str = Depends(security)):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path
        )
        request = requests.Request()
        credentials.refresh(request)
        return id_token.verify_oauth2_token(
            id_token_header, request
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e