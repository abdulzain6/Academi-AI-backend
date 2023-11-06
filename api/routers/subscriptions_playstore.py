from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status

from api.lib.database.purchases import SubscriptionType
from ..auth import get_user_id, verify_play_integrity, verify_google_token
from ..globals import subscription_checker, subscription_manager
from ..config import APP_PACKAGE_NAME, PRODUCT_ID_MAP
from pydantic import BaseModel
import logging

router = APIRouter()

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
    
class SubscriptionData(BaseModel):
    purchase_token: str

class SubscriptionUpdate(BaseModel):
    sub_type: SubscriptionType

class Notification(BaseModel):
    version: str
    notificationType: SubscriptionStatus
    purchaseToken: str
    subscriptionId: str



@router.post("/verify")
def verify_subscription(
    subscription_data: SubscriptionData,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if subscription_manager.purchase_token_exists(subscription_data.purchase_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        )
    
        
    try:    
        data = subscription_checker.check_subscription(APP_PACKAGE_NAME, subscription_data.purchase_token)
        subscription_state = data.get('subscriptionState', '')
        if subscription_state == 'SUBSCRIPTION_STATE_ACTIVE':
            if line_items := data.get('lineItems', []):
                if product_id := line_items[0].get('productId'):
                    subscription_type = PRODUCT_ID_MAP[product_id]
                    subscription_manager.apply_or_default_subscription(
                        user_id=user_id,
                        purchase_token=subscription_data.purchase_token,
                        subscription_type=subscription_type,
                        update=True
                    )
                    logging.info(f"{user_id} Just subscribed {subscription_data.purchase_token}")
                    return {"status" : "success"}   
    except Exception as e:
        logging.error(e, "Error in verify subscription")
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Token verification failed."
    )
    
@router.post("/rtdn")
def receive_notification(notification: dict, token_verified=Depends(verify_google_token)):
    notification = notification.get("subscriptionNotification")
    if not notification:
        logging.warning(notification)
        return
    
    notification["notificationType"] = SubscriptionStatus(notification["notificationType"])
    notification = Notification.model_validate(notification)
    
    logging.info(f"Recieved notification {notification}")
    
    if notification.notificationType in [SubscriptionStatus.SUBSCRIPTION_EXPIRED, SubscriptionStatus.SUBSCRIPTION_REVOKED]:
        if sub_doc := subscription_manager.get_subscription_by_token(notification.purchaseToken):
            subscription_manager.apply_or_default_subscription(
                user_id=sub_doc["user_id"],
                purchase_token="",
                subscription_type=SubscriptionType.FREE,
                update=True
            )
            logging.info(f"{sub_doc['user_id']} Just unsubscribed {notification.purchaseToken}")

    elif notification.notificationType in [SubscriptionStatus.SUBSCRIPTION_PAUSED]:
        if sub_doc := subscription_manager.get_subscription_by_token(notification.purchaseToken):
            subscription_manager.enable_disable_subscription(sub_doc["user_id"], False)
            logging.info(f"{sub_doc['user_id']} got disabled {notification.notificationType} {notification.purchaseToken}")

    elif notification.notificationType == SubscriptionStatus.SUBSCRIPTION_RESTARTED:
        if sub_doc := subscription_manager.get_subscription_by_token(notification.purchaseToken):
            subscription_manager.enable_disable_subscription(sub_doc["user_id"], True)
            logging.info(f"{sub_doc['user_id']} got enabled {notification.notificationType} {notification.purchaseToken}")
            


    return {"status": "success"}