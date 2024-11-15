from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status
from api.lib.database.purchases import SubscriptionType
from ..auth import get_user_id, verify_play_integrity, verify_google_token
from ..globals import subscription_checker, subscription_manager, user_points_manager
from ..config import APP_PACKAGE_NAME, PRODUCT_ID_MAP, PRODUCT_ID_COIN_MAP, SUB_COIN_MAP
from pydantic import BaseModel
from ..globals import log_manager as logging

router = APIRouter()

class OneTimeNotficationTypes(Enum):
    ONE_TIME_PRODUCT_PURCHASED = 1
    ONE_TIME_PRODUCT_CANCELED = 2
    
class SubscriptionStatus(Enum):
    SUBSCRIPTION_RECOVERED = 1
    SUBSCRIPTION_RENEWED = 2
    SUBSCRIPTION_CANCELED = 3
    SUBSCRIPTION_PURCHASED = 4
    SUBSCRIPTION_ON_HOLD = 5
    SUBSCRIPTION_IN_GRACE_PERIOD = 6
    SUBSCRIPTION_RESTARTED = 7
    SUBSCRIPTION_PRICE_CHANGE_CONFIRMED = 8
    SUBSCRIPTION_DEFERRED = 9
    SUBSCRIPTION_PAUSED = 10
    SUBSCRIPTION_PAUSE_SCHEDULE_CHANGED = 11
    SUBSCRIPTION_REVOKED = 12
    SUBSCRIPTION_EXPIRED = 13
    
class VoidedProductTypes(Enum):
    PRODUCT_TYPE_SUBSCRIPTION = 1
    PRODUCT_TYPE_ONE_TIME = 2
    
class SubscriptionData(BaseModel):
    purchase_token: str
    
class OneTimeData(BaseModel):
    purchase_token: str
    product_id: str

class SubscriptionUpdate(BaseModel):
    sub_type: SubscriptionType

class Notification(BaseModel):
    version: str
    notificationType: SubscriptionStatus
    purchaseToken: str
    subscriptionId: str


@router.post("/verify-onetime")
def verify_onetime(
    onetime_data: OneTimeData,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Coins purchase attempt by {user_id} Data: {onetime_data}")
    if onetime_data.purchase_token in subscription_manager.retrieve_onetime_tokens(user_id):
        logging.error(f"Coins purchase attempt by {user_id}. Tokens already used.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        )
    try:
        subscription_checker.check_one_time_purchase(APP_PACKAGE_NAME, onetime_data.purchase_token, product_id=onetime_data.product_id)
        subscription_manager.add_onetime_token(user_id=user_id, token=onetime_data.purchase_token, product_purchased=onetime_data.product_id)
        user_points_manager.increment_user_points(user_id, points=PRODUCT_ID_COIN_MAP[onetime_data.product_id])
        logging.info(f"Coins purchase attempt by {user_id}. Coins granted.")
        return {"status" : "success"}   
    except Exception as e:
        logging.error(f"Error in verify subscription {e}")
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Token verification failed."
    )
    
@router.post("/verify")
def verify_subscription(
    subscription_data: SubscriptionData,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if subscription_manager.purchase_sub_token_exists(subscription_data.purchase_token):
        logging.info(f"Subscription purchase attempt by {user_id}. Tokens already used.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        )
    else:
        subscription_manager.add_subscription_token(user_id, subscription_data.purchase_token)

    logging.info(f"Subscription purchase attempt by {user_id}")

    try:    
        data = subscription_checker.check_subscription(APP_PACKAGE_NAME, subscription_data.purchase_token)
        subscription_state = data.get('subscriptionState', '')
        if subscription_state == 'SUBSCRIPTION_STATE_ACTIVE':
            if line_items := data.get('lineItems', []):
                if product_id := line_items[0].get('productId'):
                    if "6_monthly" in product_id:
                        muliplier = 6
                    elif "monthly" in product_id:
                     muliplier = 1
                    elif "yearly" in product_id:
                        muliplier = 12
                    else:
                        muliplier = 1
                    
                    if product_id not in PRODUCT_ID_MAP:
                        logging.error(f"Product not found, Data: {subscription_data} User: {user_id}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail="Product Not found"
                        )
                        
                    subscription_type = PRODUCT_ID_MAP[product_id]
                    subscription_manager.apply_or_default_subscription(
                        user_id=user_id,
                        purchase_token=subscription_data.purchase_token,
                        subscription_type=subscription_type,
                        update=True,
                        mulitplier=muliplier
                    )
                    subscription_manager.reset_monthly_limits(user_id, muliplier)
                    logging.info(f"{user_id} Just subscribed {subscription_data.purchase_token}")
                    return {"status" : "success"}   
    
    except Exception as e:
        logging.error(f"Error in verify subscription {e}")
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Token verification failed."
    )
    
    
    

def handle_expired_or_revoked(sub_notification: dict):
    user_id = subscription_manager.retrieve_user_id_by_sub_token(sub_notification['purchaseToken'])
    if user_id:
        subscription_manager.apply_or_default_subscription(
            user_id=user_id,
            purchase_token="",
            subscription_type=SubscriptionType.FREE,
            update=True
        )
        logging.info(f"{user_id} subscription updated to free tier {sub_notification['purchaseToken']}")
    else:
        logging.error(f"User not found! Notification: {sub_notification}. Couldn't Handle expiration/Revocation EVENT")

def handle_renewed(sub_notification: dict):
    user_id = subscription_manager.retrieve_user_id_by_sub_token(sub_notification['purchaseToken'])
    if user_id:
        data = subscription_checker.check_subscription(APP_PACKAGE_NAME, sub_notification['purchaseToken'])
        multiplier = calculate_multiplier(data)
        subscription_manager.allocate_coins(user_id, multiplier=multiplier)
        subscription_manager.reset_monthly_limits(user_id, multiplier)
    else:
        logging.error(f"User not found! Notififcation: {sub_notification}. Couldn't Renew Subscription")
        raise HTTPException(status_code=404, detail="Subscription document not found.")
    
def handle_purchase(user_id: str, purchase_token: str, data: dict):
    subscription_manager.add_subscription_token(user_id, purchase_token)
    logging.info(f"Subscription purchase attempt by {user_id}")
    subscription_state = data.get('subscriptionState', '')
    if subscription_state == 'SUBSCRIPTION_STATE_ACTIVE':
        if line_items := data.get('lineItems', []):
            if product_id := line_items[0].get('productId'):
                if "6_monthly" in product_id:
                    muliplier = 6
                elif "monthly" in product_id:
                    muliplier = 1
                elif "yearly" in product_id:
                    muliplier = 12
                else:
                    muliplier = 1
                
                if product_id not in PRODUCT_ID_MAP:
                    logging.error(f"Product not found, User: {user_id}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail="Product Not found"
                    )
                    
                subscription_type = PRODUCT_ID_MAP[product_id]
                subscription_manager.apply_or_default_subscription(
                    user_id=user_id,
                    purchase_token=purchase_token,
                    subscription_type=subscription_type,
                    update=True,
                    mulitplier=muliplier
                )
                subscription_manager.reset_monthly_limits(user_id, muliplier)
                logging.info(f"{user_id} Just subscribed {purchase_token}")
                return True
    return False

def calculate_multiplier(data: dict) -> int:
    product_id = data.get('lineItems')[0].get('productId')
    if "6_monthly" in product_id:
        return 6
    elif "monthly" in product_id:
        return 1
    elif "yearly" in product_id:
        return 12
    return 1

def handle_voided_subscription(voided_notification: dict):
    user_id = subscription_manager.retrieve_user_id_by_sub_token(voided_notification['purchaseToken'])
    if user_id:
        subscription_manager.apply_or_default_subscription(
            user_id=user_id,
            purchase_token="",
            subscription_type=SubscriptionType.FREE,
            update=True
        )
        logging.info(f"Subscription voided and user {user_id} changed to free tier.")
        decrement_user_coins(user_id, voided_notification)
    else:
        logging.error(f"User not found! Data: {voided_notification}")

def handle_voided_one_time(voided_notification: dict):
    uid = subscription_manager.find_user_by_token(voided_notification['purchaseToken'])
    if uid:
        product = subscription_manager.get_product_by_user_id_and_token(uid, voided_notification['purchaseToken'])
        if product:
            user_points_manager.decrement_user_points(uid, PRODUCT_ID_COIN_MAP[product])
        else:
            logging.error("Product not found")
            raise HTTPException(status_code=404, detail="Product not found")
    else:
        logging.error(f"User not found! Data: {voided_notification}")

def decrement_user_coins(user_id: str, notification: dict):
    data = subscription_checker.check_subscription(APP_PACKAGE_NAME, notification['purchaseToken'])
    product_ids = [item['productId'] for item in data.get('lineItems', [])]
    for product_id in product_ids:
        multiplier = 1
        if "6_monthly" in product_id:
            multiplier = 6
        elif "monthly" in product_id:
            multiplier = 1
        elif "yearly" in product_id:
            multiplier = 12
        coins_to_decrement = SUB_COIN_MAP.get(product_id, 0) * multiplier
        user_points_manager.decrement_user_points(user_id, coins_to_decrement)
        logging.info(f"Decrementing {coins_to_decrement} coins for {user_id}")

def handle_voided_notification(voided_notification: dict):
    product_type = VoidedProductTypes(voided_notification.get("productType"))
    if product_type == VoidedProductTypes.PRODUCT_TYPE_SUBSCRIPTION:
        handle_voided_subscription(voided_notification)
    elif product_type == VoidedProductTypes.PRODUCT_TYPE_ONE_TIME:
        handle_voided_one_time(voided_notification)

        
@router.post("/rtdn")
def receive_notification(notification: dict, token_verified=Depends(verify_google_token)):
    logging.info(f"Received notification: {notification}")
    sub_notification = notification.get("subscriptionNotification")
    voided_notification = notification.get("voidedPurchaseNotification")
    onetime_notification = notification.get("oneTimeProductNotification")
    if sub_notification:
        notification_type = SubscriptionStatus(sub_notification['notificationType'])
        if notification_type in {SubscriptionStatus.SUBSCRIPTION_EXPIRED, SubscriptionStatus.SUBSCRIPTION_REVOKED}:
            handle_expired_or_revoked(sub_notification)
        elif notification_type == SubscriptionStatus.SUBSCRIPTION_RENEWED:
            handle_renewed(sub_notification)
        elif notification_type == SubscriptionStatus.SUBSCRIPTION_PURCHASED:
            sub_doc = subscription_checker.check_subscription(
                APP_PACKAGE_NAME,
                sub_notification['purchaseToken']
            )
            if "externalAccountIdentifiers" in sub_doc:
                user_id = sub_doc["externalAccountIdentifiers"]["obfuscatedExternalAccountId"]
                handle_purchase(user_id, sub_notification['purchaseToken'], sub_doc)
                return {"status": "success"}
    elif voided_notification:
        handle_voided_notification(voided_notification)
    elif onetime_notification:
        # Purchase
        if onetime_notification["notificationType"] == 1:
            data = subscription_checker.check_one_time_purchase(
                APP_PACKAGE_NAME,
                onetime_notification["purchaseToken"],
                product_id=onetime_notification["sku"]
            )
            print(data)
            if "obfuscatedExternalAccountId" in data:
                user_id = data["obfuscatedExternalAccountId"]
                if user_id:
                    subscription_manager.add_onetime_token(user_id=user_id, token=onetime_notification["purchaseToken"], product_purchased=onetime_notification["sku"])
                    user_points_manager.increment_user_points(user_id, points=PRODUCT_ID_COIN_MAP[onetime_notification["sku"]])
                    logging.info(f"Coins purchase attempt by {user_id}. Coins granted.")
    else:
        logging.warning(f"No relavent Notification found. Notification: {notification}")
        
    return {"status": "success"}