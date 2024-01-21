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
    logging.info(f"Coins purchase attempt by {user_id}")
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
    if subscription_manager.purchase_token_exists(subscription_data.purchase_token):
        logging.info(f"Subscription purchase attempt by {user_id}. Tokens already used.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used"
        )

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
                    subscription_type = PRODUCT_ID_MAP[product_id]
                    subscription_manager.apply_or_default_subscription(
                        user_id=user_id,
                        purchase_token=subscription_data.purchase_token,
                        subscription_type=subscription_type,
                        update=True,
                        mulitplier=muliplier
                    )
                    subscription_manager.reset_monthly_limits(user_id, True, muliplier)
                    logging.info(f"{user_id} Just subscribed {subscription_data.purchase_token}")
                    return {"status" : "success"}   
    
    except Exception as e:
        logging.error(f"Error in verify subscription {e}")
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Token verification failed."
    )
    
@router.post("/rtdn")
def receive_notification(notification: dict, token_verified=Depends(verify_google_token)):
    logging.info(f"Recieved notification {notification}")
    if "subscriptionNotification" in notification:
        sub_notification = notification.get("subscriptionNotification")
        if not sub_notification:
            logging.warning(sub_notification)
            return
        
        sub_notification["notificationType"] = SubscriptionStatus(sub_notification["notificationType"])
        sub_notification = Notification.model_validate(sub_notification)
        
        logging.info(f"Recieved notification {sub_notification}")
        
        if sub_notification.notificationType in [SubscriptionStatus.SUBSCRIPTION_EXPIRED, SubscriptionStatus.SUBSCRIPTION_REVOKED]:
            if sub_doc := subscription_manager.get_subscription_by_token(sub_notification.purchaseToken):
                subscription_manager.apply_or_default_subscription(
                    user_id=sub_doc["user_id"],
                    purchase_token="",
                    subscription_type=SubscriptionType.FREE,
                    update=True
                )
                logging.info(f"{sub_doc['user_id']} Just unsubscribed {sub_notification.purchaseToken}")
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)

        elif sub_notification.notificationType in [SubscriptionStatus.SUBSCRIPTION_PAUSED]:
            if sub_doc := subscription_manager.get_subscription_by_token(sub_notification.purchaseToken):
                subscription_manager.enable_disable_subscription(sub_doc["user_id"], False)
                logging.info(f"{sub_doc['user_id']} got disabled {sub_notification.notificationType} {sub_notification.purchaseToken}")
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)
            
        elif sub_notification.notificationType == [SubscriptionStatus.SUBSCRIPTION_RESTARTED, SubscriptionStatus.SUBSCRIPTION_RECOVERED]:
            if sub_doc := subscription_manager.get_subscription_by_token(sub_notification.purchaseToken):
                subscription_manager.enable_disable_subscription(sub_doc["user_id"], True)
                subscription_manager.cancel_uncancel_subscription(sub_doc["user_id"], False)
                logging.info(f"{sub_doc['user_id']} got enabled {sub_notification.notificationType} {sub_notification.purchaseToken}")
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)
                  
        elif sub_notification.notificationType == SubscriptionStatus.SUBSCRIPTION_CANCELED:
            if sub_doc := subscription_manager.get_subscription_by_token(sub_notification.purchaseToken):
                subscription_manager.cancel_uncancel_subscription(sub_doc["user_id"], True)
                logging.info(f"{sub_doc['user_id']} got cancelled {sub_notification.notificationType} {sub_notification.purchaseToken}")
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)
            
        elif sub_notification.notificationType == SubscriptionStatus.SUBSCRIPTION_RENEWED:
            if sub_doc := subscription_manager.get_subscription_by_token(sub_notification.purchaseToken):
                data = subscription_checker.check_subscription(APP_PACKAGE_NAME, sub_notification.purchaseToken)
                prod_id = data.get('lineItems')[0].get('productId')
                if "6_monthly" in prod_id:
                    muliplier = 6
                elif "monthly" in prod_id:
                    muliplier = 1
                elif "yearly" in prod_id:
                    muliplier = 12
                else:
                    muliplier = 1
                subscription_manager.allocate_monthly_coins(sub_doc["user_id"], multiplier=muliplier)
                subscription_manager.reset_monthly_limits(sub_doc["user_id"], True, muliplier)
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)
            
        return {"status": "success"}
    elif "voidedPurchaseNotification" in notification:
        voided_notification = notification.get("voidedPurchaseNotification")
        product_type = VoidedProductTypes(voided_notification.get("productType"))
        if product_type.PRODUCT_TYPE_SUBSCRIPTION:
            if sub_doc := subscription_manager.get_subscription_by_token(voided_notification.get("purchaseToken")):
                subscription_manager.apply_or_default_subscription(
                    user_id=sub_doc["user_id"],
                    purchase_token="",
                    subscription_type=SubscriptionType.FREE,
                    update=True
                )
                logging.info(f"Subscription Voided {sub_doc['user_id']} Chenged to free tier.", )
            else:
                logging.error("Document not found !")
                raise HTTPException(detail="Document not found.", status_code=400)
            
            if uid := subscription_manager.retrieve_user_id_by_token(voided_notification.get("purchaseToken")):
                data = subscription_checker.check_subscription(APP_PACKAGE_NAME, voided_notification.get("purchaseToken"))
                product_ids = [item['productId'] for item in data.get('lineItems', [])]
                for product_id in product_ids:
                    if "6_monthly" in product_id:
                        muliplier = 6
                    elif "monthly" in product_id:
                        muliplier = 1
                    elif "yearly" in product_id:
                        muliplier = 12
                    else:
                        muliplier = 1
                    logging.info(f"Decrementing {PRODUCT_ID_MAP[product_id] * muliplier} coins for {uid}")
                    user_points_manager.decrement_user_points(uid, SUB_COIN_MAP[product_id] * muliplier)
            else:
                logging.error("uid not found !")
                raise HTTPException(detail="uid not found.", status_code=400)
            
            logging.info(f"{uid} Just unsubscribed (Voided Notification) {voided_notification.get('purchaseToken')}")            
        elif product_type.PRODUCT_TYPE_ONE_TIME:
            uid = subscription_manager.find_user_by_token(voided_notification.get("purchaseToken"))
            product = subscription_manager.get_product_by_user_id_and_token(uid, voided_notification.get("purchaseToken"))
            if not product:
                logging.error("Product not found")
                raise HTTPException(400, detail="Product not found")
            user_points_manager.decrement_user_points(uid, PRODUCT_ID_COIN_MAP[product])

        return {"status": "success"}
