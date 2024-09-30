from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jwt import PyJWKClient
import base64
import json
import jwt

router = APIRouter()

# Apple public key endpoint for signature validation
APPLE_JWK_URL = "https://appleid.apple.com/auth/keys"

# Pydantic model for the incoming payload
class NotificationPayload(BaseModel):
    signedPayload: str

# Function to decode base64 URL-encoded strings
def base64_url_decode(input_str: str) -> bytes:
    padding = '=' * (4 - len(input_str) % 4)
    return base64.urlsafe_b64decode(input_str + padding)

# Function to verify the JWS signature
def verify_jws(signed_payload: str, apple_jwk_url: str) -> dict:
    jwk_client = PyJWKClient(apple_jwk_url)
    header = jwt.get_unverified_header(signed_payload)
    signing_key = jwk_client.get_signing_key_from_jwt(signed_payload)

    try:
        # Verify the signature and return the decoded payload
        decoded_payload = jwt.decode(signed_payload, signing_key.key, algorithms=[header['alg']])
        return decoded_payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Signature has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

@router.post("/notifications/v2")
def handle_notification(payload: NotificationPayload):
    # Verify the JWS signature
    try:
        decoded_payload = verify_jws(payload.signedPayload, APPLE_JWK_URL)
    except HTTPException as e:
        return {"error": str(e)}
    

    # Decode the payload if signature is valid
    jws_parts = payload.signedPayload.split('.')
    decoded_payload_bytes = base64_url_decode(jws_parts[1])
    decoded_payload_json = json.loads(decoded_payload_bytes)

    print(decoded_payload_json)
    # Process the notification based on its type
    notification_type = decoded_payload_json.get("notificationType")
    subtype = decoded_payload_json.get("subtype")
    
    # Custom logic to handle different notification types can be added here
    # For now, we simply return the notification type and subtype
    return {
        "notification_type": notification_type,
        "subtype": subtype,
        "decoded_payload": decoded_payload_json
    }


