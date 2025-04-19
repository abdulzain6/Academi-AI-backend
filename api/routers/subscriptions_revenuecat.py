from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..lib.database.purchases import SubscriptionType
from ..config import (
    REVENUE_CAT_WEBHOOK_TOKEN,
    PRODUCT_ID_COIN_MAP,
    SUB_COIN_MAP_REVENUE_CAT,
    PRODUCT_ID_MAP_REVENUE_CAT,
)
from ..globals import (
    subscription_manager,
    user_points_manager,
    anonymous_id_mapping,
    cust_io_client,
    user_manager,
)
from ..globals import log_manager as logging

router = APIRouter()

security = HTTPBearer()


def subscription_usage(
    purchased_at_ms: int, expiration_at_ms: int, event_timestamp_ms: int
) -> float:
    logging.info(
        f"Calculating subscription usage: purchased_at_ms={purchased_at_ms}, expiration_at_ms={expiration_at_ms}, event_timestamp_ms={event_timestamp_ms}"
    )
    total_duration = expiration_at_ms - purchased_at_ms
    elapsed_time = event_timestamp_ms - purchased_at_ms
    if total_duration == 0:
        return 0
    logging.info(
        f"Calculating subscription usage: total_duration={total_duration}, elapsed_time={elapsed_time}"
    )
    usage = (
        min(max((elapsed_time / total_duration) * 100, 0), 100) / 100
    )  # Clamp between 0-100
    logging.info(f"Calculated subscription usage: {usage}%")
    return usage


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = REVENUE_CAT_WEBHOOK_TOKEN
    logging.info(f"Verifying token: {credentials.credentials}")
    if credentials.credentials != token:
        logging.warning("Invalid token provided")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        )
    logging.info("Token verified successfully")


def get_multiplier(product_id: str) -> float:
    if product_id == "pro_monthly:pro-yearly":
        multiplier = 12
    elif "monthly" in product_id:
        multiplier = 1
    elif "weekly" in product_id:
        multiplier = 0.25
    elif "yearly" in product_id:
        multiplier = 12
    else:
        multiplier = 1
    logging.info(f"Multiplier for product {product_id}: {multiplier}")
    return multiplier


def handle_subscription_purchase(
    user_id: str,
    purchase_token: str,
    product_id: str,
    purchase_ms: float,
    expire_ms: float,
):
    subscription_manager.add_subscription_token(user_id, purchase_token)
    logging.info(
        f"Subscription purchase/renewal attempt by {user_id} with token {purchase_token}"
    )

    multiplier = get_multiplier(product_id)
    if product_id not in PRODUCT_ID_MAP_REVENUE_CAT:
        logging.error(
            f"Product not found for User: {user_id} with Product ID: {product_id}"
        )
        return

    subscription_type = PRODUCT_ID_MAP_REVENUE_CAT[product_id]
    subscription_manager.apply_or_default_subscription(
        user_id=user_id,
        purchase_token=purchase_token,
        subscription_type=subscription_type,
        update=True,
        mulitplier=multiplier,
        product_id=product_id,
        purchase_at_ms=purchase_ms,
        expiration_at_ms=expire_ms,
    )
    subscription_manager.reset_monthly_limits(user_id, multiplier)
    logging.info(
        f"{user_id} subscribed with token {purchase_token} for product {product_id}"
    )


@router.post("/revenue-cat-webhook", dependencies=[Depends(verify_token)])
def revenue_cat_webhook(request: dict):
    event = request.get("event", {})
    product_id = event.get("product_id")
    transaction_id = event.get("original_transaction_id")
    event_type = event.get("type")
    period_type = event.get("period_type")
    event_timestamp_ms = event.get("event_timestamp_ms")
    purchased_at_ms = event.get("purchased_at_ms")
    expiration_at_ms = event.get("expiration_at_ms")
    new_product_id = event.get("new_product_id")
    user_id = event.get("app_user_id")

    if anonymous_id_mapping.get_uid_by_anonymous_id(user_id):
        user_id = anonymous_id_mapping.get_uid_by_anonymous_id(user_id)

    logging.info(f"RevenueCat webhook received: {event}")

    if product_id in PRODUCT_ID_COIN_MAP:
        logging.info(f"Processing coin related event for {user_id}")
        if event_type == "NON_RENEWING_PURCHASE":
            if transaction_id in subscription_manager.retrieve_onetime_tokens(user_id):
                logging.error(
                    f"Coins purchase attempt by {user_id} with transaction ID: {transaction_id}. Tokens already used."
                )
                logging.info(
                    f"User coins: {user_points_manager.get_user_points(user_id)}"
                )
                return
            subscription_manager.add_onetime_token(
                user_id=user_id, token=transaction_id, product_purchased=product_id
            )
            user_points_manager.increment_user_points(
                user_id, points=PRODUCT_ID_COIN_MAP[product_id]
            )
            logging.info(
                f"Coins purchase granted for {user_id}. Transaction ID: {transaction_id}."
            )
        elif event_type == "CANCELLATION":
            coins = PRODUCT_ID_COIN_MAP[product_id]
            coins_to_decrement = coins * get_multiplier(product_id)
            user_points_manager.decrement_user_points(user_id, int(coins_to_decrement))
            logging.info(
                f"{user_id} had a refund. Coins decremented: {coins_to_decrement}."
            )

    elif product_id in PRODUCT_ID_MAP_REVENUE_CAT:
        logging.info(f"Processing subscription related event for {user_id}")
        if event_type == "INITIAL_PURCHASE" or event_type == "RENEWAL":
            handle_subscription_purchase(
                user_id,
                transaction_id,
                product_id,
                purchase_ms=purchased_at_ms,
                expire_ms=expiration_at_ms,
            )
            user = user_manager.get_user_by_uid(user_id)
            if user:
                if event_type == "INITIAL_PURCHASE":
                    cust_io_client.send_event(
                        user_id,
                        "subscription_confirmation",
                        {
                            "email": user.email,
                            "first_name": user.display_name,
                            "subscription_renewal_date": datetime.fromtimestamp(
                                expiration_at_ms / 1000.0
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                        },
                    )
                elif event_type == "RENEWAL":
                    cust_io_client.send_event(
                        user_id,
                        "subscription_renewal",
                        {
                            "email": user.email,
                            "first_name": user.display_name,
                        },
                    )
            else:
                logging.info(f"User {user_id} not found in the database.")

        elif event_type == "EXPIRATION":
            user_sub = subscription_manager.fetch_or_cache_subscription(user_id=user_id)
            logging.info(
                f"Subscription expired for {user_id} with transaction ID: {transaction_id}"
            )
            if period_type == "TRIAL":
                coins = SUB_COIN_MAP_REVENUE_CAT[product_id]
                coins_to_decrement = coins * get_multiplier(product_id)
                user_points_manager.decrement_user_points(
                    user_id, int(coins_to_decrement)
                )
                logging.info(
                    f"{user_id} trial expired. Coins decremented: {coins_to_decrement}"
                )

            if user_sub.get("purchase_token") == transaction_id:
                subscription_manager.apply_or_default_subscription(
                    user_id=user_id,
                    purchase_token="",
                    subscription_type=SubscriptionType.FREE,
                    update=True,
                )
                logging.info(f"{user_id} subscription set to free due to expiration.")

        elif event_type == "CANCELLATION":
            reason = event["cancel_reason"]
            logging.info(f"{user_id} subscription cancellation. Reason: {reason}")
            if reason == "CUSTOMER_SUPPORT":
                user_sub = subscription_manager.fetch_or_cache_subscription(
                    user_id=user_id
                )
                if user_sub.get("purchase_token") == transaction_id:
                    subscription_manager.apply_or_default_subscription(
                        user_id=user_id,
                        purchase_token="",
                        subscription_type=SubscriptionType.FREE,
                        update=True,
                    )
                    coins = SUB_COIN_MAP_REVENUE_CAT[product_id]
                    coins = get_multiplier(product_id) * coins
                    user_points_manager.decrement_user_points(user_id, int(coins))
                    logging.info(
                        f"{user_id} coins decremented due to customer support cancellation. Coins: {coins}"
                    )
            else:
                logging.info(f"Unhandled cancellation reason for {user_id}: {reason}")

        elif event_type == "PRODUCT_CHANGE":
            sub = subscription_manager.fetch_or_cache_subscription(user_id=user_id)
            logging.info(f"{sub}")
            percentage_used = subscription_usage(
                sub.get("purchase_at_ms", 0),
                sub.get("expiration_at_ms", 0),
                event_timestamp_ms,
            )
            coins = SUB_COIN_MAP_REVENUE_CAT[product_id]
            coins = get_multiplier(product_id) * coins
            coins_to_decrement = coins * percentage_used
            user_points_manager.decrement_user_points(user_id, int(coins_to_decrement))
            logging.info(
                f"{user_id} coins decremented due to product change. Coins: {coins_to_decrement}"
            )

            subscription_manager.apply_or_default_subscription(
                user_id=user_id,
                purchase_token=transaction_id,
                subscription_type=SubscriptionType.PRO,
                update=True,
                product_id=new_product_id,
                mulitplier=get_multiplier(new_product_id),
                purchase_at_ms=purchased_at_ms,
                expiration_at_ms=expiration_at_ms,
            )
            subscription_manager.reset_monthly_limits(
                user_id, get_multiplier(new_product_id)
            )
            logging.info(
                f"Subscription updated for {user_id} due to product change. New product ID: {new_product_id}"
            )

        else:
            logging.info(f"Unhandled Event for {user_id}: {event}")
    else:
        logging.info(
            f"Unhandled product ID for user {user_id}: {product_id}, Event: {event}"
        )

    logging.info(f"Event processing completed for {user_id}")
    return {"status": "success"}
