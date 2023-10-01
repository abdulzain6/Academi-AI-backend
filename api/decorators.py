from .config import FEATURE_PRICING
from .globals import user_points_manager
from .auth import get_user_id
from fastapi import HTTPException, Depends



def require_points_for_feature(feature_key: str):
    def dependency(user_id: str = Depends(get_user_id)) -> None:

        user_points_data = user_points_manager.get_user_points(user_id)
        user_points = user_points_data.points if user_points_data else 0

        required_points = FEATURE_PRICING.get(feature_key, 0)
        if user_points < required_points:
            raise HTTPException(status_code=403, detail="Insufficient points")

        user_points_manager.decrement_user_points(user_id, required_points)
    return dependency
