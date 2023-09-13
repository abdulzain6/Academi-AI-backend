from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from .firebase import default_app
from fastapi import Depends, HTTPException, status
import logging


security = HTTPBearer()

def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        token = credentials.credentials
        logging.info(f"Verifying token {token}")
        user = auth.verify_id_token(token, app=default_app)
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
        logging.info(f"Verifying token {token}")
        user = auth.verify_id_token(token, app=default_app)
        user_details = auth.get_user(user["user_id"])
        return {
            "email": user_details.email,
            "user_id": user["user_id"],
            "display_name": user_details.display_name,
            "photo_url": user_details.photo_url,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e