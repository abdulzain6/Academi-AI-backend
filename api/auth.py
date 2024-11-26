from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from fastapi import Depends, HTTPException, Header, status
from fastapi import Request
from firebase_admin import app_check
from google.oauth2 import id_token
from google.auth.transport import requests
from google.oauth2 import service_account
from .globals import credentials_path, redis_cache_manager, email_checker, user_location_db, ip_locator
from .firebase import default_app
from .config import API_KEY_BACKDOOR, CRONJOB_KEY
from .lib.database.user_city_country import UserLocation

import logging
import jwt


security = HTTPBearer()



class FraudException(Exception):
    pass




def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security), request: Request = None) -> str:
    token = credentials.credentials
    cache_key = f"token_new:{token}"
    
    # Get the client's IP address
    if request:
        ip_address = request.headers.get('X-Forwarded-For', request.client.host)
        ip_address = ip_address.split(',')[0].strip() if ip_address else None
    else:
        ip_address = None

    try:
        user_id = get_set_user_id(cache_key, token)
        
        try:
            if not user_location_db.get_location(user_id=user_id) and ip_address:
                location = ip_locator.get_location_from_ip(ip_address)
                assert "country" in location
                logging.info(f"User {user_id} is from {location.get('country')}, {location.get('city')}")
                user_location_db.create_location(
                    UserLocation(user_id=user_id, city=location.get("city"), country=location.get("country"))
                )
        except Exception as e:
            print(e)
            logging.error(f"Error finding location for IP: {ip_address}, User: {user_id}")
        
        # Log the IP address along with the user ID
        if ip_address:
            logging.info(f"User ID: {user_id}, IP Address: {ip_address}")
        
        return user_id
    except FraudException as e:
        logging.error(f"Fraud detected - Token: {token}, IP: {ip_address}, Error: {e}")
        redis_cache_manager.delete(cache_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account has been banned because of fraud, please contact customer support!",
            headers={"WWW-Authenticate": "Bearer"},
        )     
    except Exception as e:
        logging.error(f"Authentication error - Token: {token}, IP: {ip_address}, Error: {e}")
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
    if not email_checker.is_valid_email(auth.get_user(user_id).email):
        raise FraudException(f"Fraud detected {user_id}")
    
    logging.info("Verified token, storing in cache...")
    redis_cache_manager.set(cache_key, user_id)
    return user_id

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    cache_key = f"user_details_new:{token}"

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
        if not email_checker.is_valid_email(user_details.email):
            raise FraudException("Invalid Email, Fraud Detected!")
        
        redis_cache_manager.set(cache_key, user_data)
        return user_data
    except FraudException:
        logging.error(f"Fraud detected {user_data}")
        redis_cache_manager.delete(cache_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account has been banned because of fraud, please contact customer support!",
            headers={"WWW-Authenticate": "Bearer"},
        )        
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