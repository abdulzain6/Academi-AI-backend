import logging

from api.lib.database.purchases import SubscriptionType
from .config import FEATURE_PRICING, FILE_COLLECTION_LIMITS
from .globals import (
    user_points_manager,
    subscription_manager,
    file_manager,
    collection_manager,
)
from fastapi import HTTPException
from functools import wraps
from langchain.callbacks import get_openai_callback
from typing import Callable, Any, Optional, Union
from inspect import isfunction


def require_points_for_feature(feature_key: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for key, value in kwargs.items():
                if isfunction(value):
                    resolved_value = value()
                    kwargs[key] = resolved_value

            user_id = kwargs.get("user_id")
            logging.info(
                f"Checking points for feature: {feature_key} and user: {user_id}"
            )

            user_points_data = user_points_manager.get_user_points(user_id)
            user_points = user_points_data.points if user_points_data else 0

            required_points = FEATURE_PRICING.get(feature_key, 0)

            if user_points < required_points:
                logging.warning(
                    f"Insufficient points for user: {user_id} on feature: {feature_key}"
                )
                raise HTTPException(status_code=403, detail="Insufficient points")

            user_points_manager.decrement_user_points(user_id, required_points)
            logging.info(
                f"Points decremented for user: {user_id} on feature: {feature_key}"
            )

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logging.error(
                    f"An error occurred: {e}. Refunding points for user: {user_id} on feature: {feature_key}"
                )
                user_points_manager.increment_user_points(user_id, required_points)
                if isinstance(e, HTTPException):
                    raise e
                
                raise HTTPException(500, detail=str(e))

        return wrapper

    return decorator


def use_feature(feature_name: str, user_id: str) -> tuple[bool, str | int]:
    logging.info(f"Checking if {user_id} can use feature: {feature_name}")
    can_use, feature = subscription_manager.can_use_feature(user_id, feature_name)
    logging.info(
        f"{user_id} {'can use' if can_use else 'cannot use'} feature: {feature_name}... Main value {feature}"
    )

    if not can_use:
        raise HTTPException(400, detail="Limit reached, User cannot use feature")

    used = subscription_manager.use_feature(user_id, feature_name)
    return used, feature


def use_feature_with_premium_model_check(
    feature_name: str, user_id: str
) -> tuple[Optional[Union[str, int]], bool]:
    used, feature = use_feature(feature_name, user_id)
    if subscription_manager.get_subscription_type(user_id) == SubscriptionType.ELITE:
        used_gpt, feature_gpt = use_feature("MODEL", user_id)
        return feature_gpt, used_gpt
    return None, False


def can_use_premium_model(user_id: str) -> tuple[Optional[Union[str, int]], bool]:
    if subscription_manager.get_subscription_type(user_id) == SubscriptionType.ELITE:
        used_gpt, feature_gpt = use_feature("MODEL", user_id)
        return feature_gpt, used_gpt
    return None, False


def openai_token_tracking_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with get_openai_callback() as cb:
            response: Any = func(*args, **kwargs)
            print(f"Total tokens used: {cb.total_tokens}")
            print(f"Total cost: {cb.total_cost}")
        return response

    return wrapper


def can_add_more_data(
    user_id: str,
    collection_name: str = None,
    collection_check: bool = True,
    file_check: bool = True,
):
    subscription = subscription_manager.get_subscription_type(user_id)
    if subscription != SubscriptionType.FREE:
        return

    if collection_name and file_check:
        file_count = len(
            file_manager.get_all_files(user_id=user_id, collection_name=collection_name)
        )
        if file_count >= FILE_COLLECTION_LIMITS[SubscriptionType.FREE]:
            raise HTTPException(400, detail="File limit reached, cannot add more files")

    collection_count = len(collection_manager.get_all_by_user(user_id))
    if collection_count >= FILE_COLLECTION_LIMITS[SubscriptionType.FREE] and collection_check:
        raise HTTPException(
            400, detail="Collection/Subject limit reached, cannot add more"
        )
