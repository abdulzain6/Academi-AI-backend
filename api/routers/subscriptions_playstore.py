from fastapi import APIRouter, Depends, HTTPException, status

from api.lib.database.purchases import SubscriptionType
from ..auth import get_user_id, verify_play_integrity
from ..globals import subscription_checker, subscription_manager
from pydantic import BaseModel

router = APIRouter()


class SubscriptionData(BaseModel):
    purchase_token: str
    package_name: str
    subscription_id: str

class SubscriptionUpdate(BaseModel):
    sub_type: SubscriptionType


@router.post("/verify")
def verify_subscription(
    subscription_data: SubscriptionData,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if is_valid := subscription_checker.check_subscription(
        subscription_data.package_name,
        subscription_data.subscription_id,
        subscription_data.purchase_token,
    ):
        return {"status": "success"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid purchase token"
        )

@router.post("/update")
def update_subscription(
    subscription_data: SubscriptionUpdate,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    subscription_manager.apply_or_default_subscription(
        user_id, subscription_data.sub_type, update=True
    )
    
@router.post("/rtdn")
async def receive_notification(notification: dict):
    print(notification)
    return {}
    
    notification_type = notification.notificationType
    token = notification.purchaseToken
    subscription_id = notification.subscriptionId

    cache_key = f"{subscription_id}:{token}"

    if notification_type in ["SUBSCRIPTION_PURCHASED", "SUBSCRIPTION_RENEWED"]:
        subscription_cache.cache_subscription_status(cache_key, True)
    elif notification_type in ["SUBSCRIPTION_CANCELED", "SUBSCRIPTION_EXPIRED"]:
        subscription_cache.cache_subscription_status(cache_key, False)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unhandled notification type: {notification_type}"
        )
    return {"status": "success"}