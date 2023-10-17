import logging
from .config import FEATURE_PRICING
from .globals import user_points_manager
from .auth import get_user_id
from fastapi import HTTPException, Depends
from functools import wraps
from langchain.callbacks import get_openai_callback
from typing import Callable, Any
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
            logging.info(f"Checking points for feature: {feature_key} and user: {user_id}")
            
            user_points_data = user_points_manager.get_user_points(user_id)
            user_points = user_points_data.points if user_points_data else 0

            required_points = FEATURE_PRICING.get(feature_key, 0)

            if user_points < required_points:
                logging.warning(f"Insufficient points for user: {user_id} on feature: {feature_key}")
                raise HTTPException(status_code=403, detail="Insufficient points")

            user_points_manager.decrement_user_points(user_id, required_points)
            logging.info(f"Points decremented for user: {user_id} on feature: {feature_key}")

            try:
                return func(*args, **kwargs)
            except Exception as e:
                logging.error(f"An error occurred: {e}. Refunding points for user: {user_id} on feature: {feature_key}")
                user_points_manager.increment_user_points(user_id, required_points)
                raise e

        return wrapper

    return decorator


def openai_token_tracking_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with get_openai_callback() as cb:
            response: Any = func(*args, **kwargs)
            print(f"Total tokens used: {cb.total_tokens}")
            print(f"Total cost: {cb.total_cost}")
        return response

    return wrapper
