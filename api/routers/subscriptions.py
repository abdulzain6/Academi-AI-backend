import logging
from fastapi import APIRouter, Depends
from ..auth import get_user_id, verify_play_integrity, verify_cronjob_request
from ..globals import subscription_manager, user_manager

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
    
@router.get("/usage-limits")
def get_usage_limits(
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    return {
        "limits" : subscription_manager.get_all_feature_usage_left(user_id)
    }
    
@router.get("/reset")
def reset_usage_job(
    verify=Depends(verify_cronjob_request),
):
    for user in user_manager.get_all():
        try:
            subscription_manager.reset_all_limits(user.uid)
        except Exception as e:
            logging.error(f"Error in reseting limit for {user.uid}. {e}")
    logging.info("Successfully reset limits")