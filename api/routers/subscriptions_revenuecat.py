from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..lib.database.purchases import SubscriptionType
from ..config import REVENUE_CAT_WEBHOOK_TOKEN, PRODUCT_ID_COIN_MAP, SUB_COIN_MAP_REVENUE_CAT, PRODUCT_ID_MAP_REVENUE_CAT
from ..globals import subscription_manager, user_points_manager
from ..globals import log_manager as logging


router = APIRouter()

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = REVENUE_CAT_WEBHOOK_TOKEN
    if credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        )
    
def get_multiplier(product_id: str) -> float:
    """Determine the subscription multiplier based on the product ID."""
    if "monthly" in product_id:
        return 1
    elif "weekly" in product_id:
        return 0.25
    elif "yearly" in product_id:
        return 12
    else:
        return 1


def handle_subscription_renewal(user_id: str, product_id: str):
    multiplier = get_multiplier(product_id)
    subscription_manager.allocate_coins(user_id, multiplier=multiplier)
    subscription_manager.reset_monthly_limits(user_id, multiplier)


def handle_subscription_purchase(user_id: str, purchase_token: str, product_id: str):
    subscription_manager.add_subscription_token(user_id, purchase_token)
    logging.info(f"Subscription purchase attempt by {user_id}")

    muliplier = get_multiplier(product_id)
    if product_id not in PRODUCT_ID_MAP_REVENUE_CAT:
        logging.error(f"Product not found, User: {user_id}")
        return
    
    subscription_type = PRODUCT_ID_MAP_REVENUE_CAT[product_id]
    subscription_manager.apply_or_default_subscription(
        user_id=user_id,
        purchase_token=purchase_token,
        subscription_type=subscription_type,
        update=True,
        mulitplier=muliplier,
        product_id=product_id
    )
    subscription_manager.reset_monthly_limits(user_id, muliplier)
    logging.info(f"{user_id} Just subscribed {purchase_token}")


@router.post("/revenue-cat-webhook", dependencies=[Depends(verify_token)])
def revenue_cat_webhook(request: dict):
    event = request.get("event", {})
    product_id = event.get("product_id")
    user_id = event.get("app_user_id")
    transaction_id = event.get("transaction_id")
    event_type = event.get("type")
    period_type = event.get("period_type")
    
    logging.info(f"RevenueCat webhook received: {event}")
    
    if product_id in PRODUCT_ID_COIN_MAP:
        if event_type == "NON_RENEWING_PURCHASE":
            if transaction_id in subscription_manager.retrieve_onetime_tokens(user_id):
                logging.error(f"Coins purchase attempt by {user_id}. Tokens already used.")
                return
            
            subscription_manager.add_onetime_token(user_id=user_id, token=transaction_id, product_purchased=product_id)
            user_points_manager.increment_user_points(user_id, points=PRODUCT_ID_COIN_MAP[product_id])
            logging.info(f"Coins purchase attempt by {user_id}. Coins granted.")
        elif event_type == "CANCELLATION":
            coins = PRODUCT_ID_COIN_MAP[product_id]
            coins_to_decrement = coins * get_multiplier(product_id)
            user_points_manager.decrement_user_points(user_id, coins_to_decrement)
            logging.info(f"{user_id}. Coins decremented. Refund scenario")
                 
    elif product_id in PRODUCT_ID_MAP_REVENUE_CAT:
        if event_type == "INITIAL_PURCHASE":
            handle_subscription_purchase(user_id, transaction_id, product_id)
        elif event_type == "RENEWAL":
            handle_subscription_renewal(user_id=user_id, product_id=product_id)
        elif event_type == "EXPIRATION":
            user_sub = subscription_manager.fetch_or_cache_subscription(user_id=user_id)
            if period_type == "TRIAL":
                coins = SUB_COIN_MAP_REVENUE_CAT[product_id]
                coins_to_decrement = coins * get_multiplier(product_id)
                user_points_manager.decrement_user_points(user_id, coins_to_decrement)
                logging.info(f"{user_id}. Coins decremented because trial expired")

            if user_sub.get("product_id") == product_id:
                subscription_manager.apply_or_default_subscription(
                    user_id=user_id,
                    purchase_token="",
                    subscription_type=SubscriptionType.FREE,
                    update=True
                )

        elif event_type == "CANCELLATION":
            reason = event["cancel_reason"]
            if reason == "CUSTOMER_SUPPORT":
                if user_sub.get("product_id") == product_id:
                    subscription_manager.apply_or_default_subscription(
                        user_id=user_id,
                        purchase_token="",
                        subscription_type=SubscriptionType.FREE,
                        update=True
                    )
                    coins = SUB_COIN_MAP_REVENUE_CAT[product_id]
                    coins = get_multiplier(product_id) * coins
                    user_points_manager.decrement_user_points(user_id, coins)
            else:
                logging.info(f"Unhandled Event : {event}.")
        else:
            logging.info(f"Unhandled Event : {event}.")
    else:
        logging.info(f"Unhandled Event : {event}.")

    return {"status": "success"}