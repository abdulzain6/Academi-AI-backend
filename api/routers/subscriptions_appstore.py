import asyncio
import json
import logging
import os
import traceback
import requests
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, HTTPException, status
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException
from appstoreserverlibrary.models.NotificationTypeV2 import NotificationTypeV2
from appstoreserverlibrary.models.Status import Status
from appstoreserverlibrary.models.Subtype import Subtype
from appstoreserverlibrary.models.ResponseBodyV2DecodedPayload import ResponseBodyV2DecodedPayload
from fastapi import Request, HTTPException
from concurrent.futures import ThreadPoolExecutor
from ..lib.database.purchases import SubscriptionProvider, SubscriptionType
from ..config import APP_PACKAGE_NAME, PRODUCT_ID_COIN_MAP, SUB_COIN_MAP
from ..globals import user_points_manager, subscription_manager, PRODUCT_ID_MAP, uuid_mapping_manager
from ..auth import get_user_id


executor = ThreadPoolExecutor()

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
            certificates.append(response.content)
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
    
   
def calculate_multiplier(product_id: str) -> int:
    if "6_monthly" in product_id:
        return 6
    elif "monthly" in product_id:
        return 1
    elif "yearly" in product_id:
        return 12
    return 1

def handle_purchase(user_id: str, transaction_id: str, product_id: str):
    subscription_manager.add_subscription_token(user_id, transaction_id)
    logging.info(f"Subscription purchase attempt by {user_id}")
    multiplier = calculate_multiplier(product_id)
    if product_id not in PRODUCT_ID_MAP:
        logging.error(f"Product not found, User: {user_id}, Product: {product_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Product Not found"
        )
        
    subscription_type = PRODUCT_ID_MAP[product_id]
    subscription_manager.apply_or_default_subscription(
        user_id=user_id,
        purchase_token=transaction_id,
        subscription_type=subscription_type,
        update=True,
        mulitplier=multiplier,
        subscription_provider=SubscriptionProvider.APPSTORE
    )
    subscription_manager.reset_monthly_limits(user_id, multiplier)
    logging.info(f"{user_id} Just subscribed {transaction_id}")

def handle_renewed(user_id: str, product_id: str):
    multiplier = calculate_multiplier(product_id=product_id)
    subscription_manager.allocate_coins(user_id, multiplier=multiplier)
    subscription_manager.reset_monthly_limits(user_id, multiplier)
    
def decrement_user_coins(user_id: str, product_id: str):
    multiplier = calculate_multiplier(product_id=product_id)
    coins_to_decrement = SUB_COIN_MAP.get(product_id, 0) * multiplier
    user_points_manager.decrement_user_points(user_id, coins_to_decrement)
    logging.info(f"Decrementing {coins_to_decrement} coins for {user_id}")
   
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
         


def process_notification(payload: ResponseBodyV2DecodedPayload, verifier: SignedDataVerifier, subscription_manager, user_points_manager):
    try:
        signed_trans_info = payload.data.signedTransactionInfo
        transaction_info = verifier.verify_and_decode_signed_transaction(signed_trans_info)
        user_id = uuid_mapping_manager.get_uid(transaction_info.appAccountToken)
        logging.info(f"UserID of user is: {user_id}")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User not found")
        
        if payload.notificationType == NotificationTypeV2.SUBSCRIBED:
            logging.info("Subscription Notification Received")
            if payload.data.status == Status.ACTIVE and payload.subtype == Subtype.INITIAL_BUY:
                handle_purchase(user_id, transaction_info.transactionId, transaction_info.productId)
            else:
                logging.info(f"Status of Subscription is not ACTIVE, It is {payload.data.status}. Subtype: {payload.subtype} Skipping...")
        
        elif payload.notificationType == NotificationTypeV2.DID_RENEW:
            logging.info("Renewal Notification Received")
            if payload.data.status == Status.ACTIVE and not payload.subtype:
                handle_renewed(user_id, transaction_info.productId)    
            else:
                logging.info(f"Status of Subscription is not ACTIVE, It is {payload.data.status}. Subtype: {payload.subtype} Skipping...")  
        
        elif payload.notificationType in [NotificationTypeV2.EXPIRED, NotificationTypeV2.REVOKE]:
            logging.info("Expiration/Revocation Notification Received")
            subscription_manager.apply_or_default_subscription(
                user_id=user_id,
                purchase_token="",
                subscription_type=SubscriptionType.FREE,
                subscription_provider=SubscriptionProvider.APPSTORE,
                update=True
            )
            logging.info(f"{user_id} subscription updated to free tier")
            
        elif payload.notificationType == NotificationTypeV2.REFUND:
            logging.info("Refund Notification Received")
            if transaction_info.productId in PRODUCT_ID_MAP:
                subscription_manager.apply_or_default_subscription(
                    user_id=user_id,
                    purchase_token="",
                    subscription_type=SubscriptionType.FREE,
                    subscription_provider=SubscriptionProvider.APPSTORE,
                    update=True
                )
                logging.info(f"Subscription voided and user {user_id} changed to free tier.")
                decrement_user_coins(user_id, transaction_info.productId)
            elif transaction_info.productId in PRODUCT_ID_COIN_MAP:
                user_points_manager.decrement_user_points(
                    user_id,
                    PRODUCT_ID_COIN_MAP[transaction_info.productId]
                )
                logging.info(f"{PRODUCT_ID_COIN_MAP[transaction_info.productId]} Coins decremented!")
            else:
                logging.info(f"Invalid product ID: {transaction_info.productId}")
                raise HTTPException(status_code=400, detail="Invalid product ID")
            
        elif payload.notificationType == NotificationTypeV2.REFUND_REVERSED:
            logging.info("Refund reversal Notification Received")
            if transaction_info.productId in PRODUCT_ID_MAP:
                handle_purchase(user_id, transaction_info.transactionId, transaction_info.productId)
            else:
                logging.info(f"Adding {PRODUCT_ID_COIN_MAP[transaction_info.productId]} coins to user: {user_id}")
                user_points_manager.increment_user_points(user_id, PRODUCT_ID_COIN_MAP[transaction_info.productId])

    except Exception as e:
        logging.error(f"Error processing notification: {str(e)}")
        raise

@router.post("/app-store-notifications/v2")
async def receive_notification(request: Request):
    try:
        # Log the headers
        logging.info(f"Received headers: {request.headers}")

        # Get the raw body of the request
        body = await request.body()
        logging.info(f"Body: {body}")
        signed_payload = body.decode()

        # Verify and decode the notification
        payload = verifier.verify_and_decode_notification(json.loads(signed_payload)["signedPayload"])
        logging.info("Received App Store Notification:")
        logging.info(payload)

        # Process the notification in the executor
        await asyncio.get_event_loop().run_in_executor(
            executor, 
            process_notification, 
            payload, 
            verifier, 
            subscription_manager, 
            user_points_manager
        )

        return {"status": "success", "message": "Notification received and processed"}

    except VerificationException as e:
        logging.error(f"Verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid notification")
    except Exception as e:
        logging.error(f"Error processing notification: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/generate-uuid")
def generate_uuid(user_id: str = Depends(get_user_id)):
    uuid_key = uuid_mapping_manager.create_mapping(user_id)
    return {"uuid_key" : uuid_key}