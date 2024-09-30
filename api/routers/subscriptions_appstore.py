import asyncio
import logging
import os
from pydantic import BaseModel
import requests
from fastapi import APIRouter, Depends, Request, HTTPException, status
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from appstoreserverlibrary.models.Environment import Environment
from ..config import APP_PACKAGE_NAME, PRODUCT_ID_COIN_MAP
from ..globals import user_points_manager, subscription_manager
from ..auth import get_user_id
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException

router = APIRouter()

APPLE_ROOT_CERT_URLS = [
    "https://www.apple.com/appleca/AppleIncRootCertificate.cer",
    "https://www.apple.com/certificateauthority/AppleComputerRootCertificate.cer",
    "https://www.apple.com/certificateauthority/AppleRootCA-G2.cer",
    "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer"
]

def load_root_certificates():
    certificates = []
    for url in APPLE_ROOT_CERT_URLS:
        try:
            response = requests.get(url)
            response.raise_for_status()
            cert = x509.load_der_x509_certificate(response.content)
            pem_cert = cert.public_bytes(encoding=serialization.Encoding.PEM)
            certificates.append(pem_cert)
        except requests.RequestException as e:
            print(f"Failed to download certificate from {url}: {e}")
        except Exception as e:
            print(f"Failed to process certificate from {url}: {e}")
    return certificates

root_certificates = load_root_certificates()
enable_online_checks = True
environment = Environment.SANDBOX
app_apple_id = None 
verifier = SignedDataVerifier(root_certificates, enable_online_checks, environment, APP_PACKAGE_NAME, app_apple_id)
app_store_client = AppStoreServerAPIClient(
    open(str(os.getenv("PRIVATE_KEY_PATH")), "rb").read(),
    os.getenv("APPSTORE_KEYID"),
    os.getenv("APPSTORE_ISSUER_ID"),
    APP_PACKAGE_NAME,
    environment
)

class OneTimeData(BaseModel):
    transaction_id: str
    product_id: str
   
   
@router.post("/verify-onetime-apple")
def verify_onetime_apple(
    onetime_data: OneTimeData,
    user_id=Depends(get_user_id),
):
    logging.info(f"Coins purchase attempt by {user_id} Data: {onetime_data}")
    
    if onetime_data.transaction_id in subscription_manager.retrieve_onetime_tokens(user_id):
        logging.error(f"Coins purchase attempt by {user_id}. Tokens already used.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        )
    
    try:
        # Verify the transaction with Apple
        transaction_info = app_store_client.get_transaction_info(onetime_data.transaction_id)
        try:
            transaction_info = verifier.verify_and_decode_signed_transaction(transaction_info.signedTransactionInfo)
        except VerificationException as ve:
            logging.error(f"Transaction verification failed: {ve}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction verification failed"
            )
        
        # Check if the transaction is valid and matches the product
        if (transaction_info.transactionId == onetime_data.transaction_id and 
            transaction_info.productId == onetime_data.product_id and
            transaction_info.revocationReason is None):
            
            # Mark the transaction as used
            subscription_manager.add_onetime_token(user_id, onetime_data.transaction_id, onetime_data.product_id)
            
            # Grant the coins
            user_points_manager.increment_user_points(user_id, points=PRODUCT_ID_COIN_MAP[onetime_data.product_id])
            
            logging.info(f"Coins purchase attempt by {user_id}. Coins granted.")
            return {"status": "success"}
        else:
            logging.error(f"Invalid transaction for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction"
            )
    
    except APIException as e:
        logging.error(f"Error in verify Apple purchase: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction verification failed."
        )
         
@router.post("/app-store-notifications")
def receive_notification(request: Request):
    try:
        # Get the raw body of the request
        body = asyncio.run(request.body())
        signed_payload = body.decode()

        # Verify and decode the notification
        payload = verifier.verify_and_decode_notification(signed_payload)

        # Print the decoded payload
        print("Received App Store Notification:")
        print(payload)

        return {"status": "success", "message": "Notification received and processed"}

    except VerificationException as e:
        print(f"Verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid notification")
    except Exception as e:
        print(f"Error processing notification: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
