from fastapi import APIRouter, Depends
from ..auth import get_user_id, verify_play_integrity
from ..globals import subscription_manager

router = APIRouter()


@router.get("/plan")
def get_subscription_plan(
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    return {
        "plan" : subscription_manager.get_subscription_type(user_id)
    }
    

@router.post("/premium_model")
def turn_on_premium_model(
    enabled: bool,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    return {
        "success" : subscription_manager.toggle_feature(user_id, "MODEL", enabled)
    }
    