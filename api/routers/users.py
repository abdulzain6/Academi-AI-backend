from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..auth import get_current_user, get_user_id, verify_play_integrity
from ..globals import (
    user_manager,
    knowledge_manager,
    subscription_manager,
    user_points_manager,
    DEFAULT_POINTS_INCREMENT,
    referral_manager,
    subscription_manager,
    conversation_manager,
)
from ..lib.database.users import UserModel
import logging

router = APIRouter()


class UserResponse(BaseModel):
    status: str
    error: str
    user: UserModel


class DeleteUserResponse(BaseModel):
    status: str
    error: str
    user: int


class UserUpdate(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    photo_url: Optional[str] = None


@router.post("/increment_points/", tags=["points", "ads"])
def increment_points(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    logging.info(f"Increment points request from {user_id}")
    if not user_points_manager.can_increment_from_ad(uid=user_id):
        raise HTTPException(detail="Ads limit reached, update the app to latest version", status_code=400)
    
    modified_count = user_points_manager.increment_user_points(
        user_id, DEFAULT_POINTS_INCREMENT
    )
    if modified_count > 0:
        return {
            "status": "success",
            "message": f"Incremented points by {DEFAULT_POINTS_INCREMENT}",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to increment points.",
        )


@router.post("/ads_watched", tags=["ads"])
def get_number_of_ads_watched(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    return {
        "ads_watched": user_points_manager.get_ads_watched_today(user_id),
        "max_allowed": user_points_manager.max_ads_per_day,
    }


@router.get("/is_daily_bonus_claimed/", tags=["points", "daily bonus"])
def is_daily_bonus_claimed(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    logging.info(f"Daily bonus claim check request from {user_id}")
    is_claimed = user_points_manager.is_daily_bonus_claimed(user_id)
    return {"status": "success", "is_claimed": is_claimed}


@router.get("/points", tags=["points", "ads"])
def get_user_points(
    current_user=Depends(get_current_user),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Get points request from {current_user['user_id']}")
    if user_points := user_points_manager.get_user_points(current_user["user_id"]):
        if model := subscription_manager.get_feature_value(
            current_user["user_id"], "MODEL"
        ):
            return {
                "points": user_points.model_dump(),
                "model": model.model_dump(),
                "model_enabled": subscription_manager.is_monthly_limit_feature_enabled(
                    current_user["user_id"], "MODEL"
                ),
            }
        return {"points": user_points.model_dump()}
    else:
        user = user_manager.add_user(
            UserModel(
                uid=current_user["user_id"],
                email=current_user["email"],
                display_name=current_user["display_name"],
                photo_url=current_user["photo_url"],
            )
        )
        if model := subscription_manager.get_feature_value(
            current_user["user_id"], "MODEL"
        ):
            return {
                "points": user_points.model_dump(),
                "model": model.model_dump(),
                "model_enabled": subscription_manager.is_monthly_limit_feature_enabled(
                    current_user["user_id"], "MODEL"
                ),
            }
        return {"points": user_points.model_dump()}


@router.post("/claim_daily_bonus/", tags=["points", "daily bonus"])
def claim_daily_bonus(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    logging.info(f"Daily bonus claim request from {user_id}")
    bonus_points = user_points_manager.claim_daily_bonus(user_id)
    if bonus_points > 0:
        return {"status": "success", "message": f"Claimed {bonus_points} bonus points"}

    time_left = user_points_manager.time_until_daily_bonus(user_id)
    human_readable_time_left = str(time_left).split(".")[0]  # Remove microseconds

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Failed to claim daily bonus. Time left until next claim: {human_readable_time_left}",
    )


@router.get("/streak_day/", tags=["points", "daily bonus"])
def get_streak_day(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    logging.info(f"Get streak day request from {user_id}")
    streak_day = user_points_manager.get_streak_day(user_id)
    return {"status": "success", "streak_day": streak_day}


@router.get("/get_referral_code/", tags=["points", "referral"])
def get_referral_code(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    logging.info(f"Get referral code request from {user_id}")
    return {"status": "success", "referral_code": user_id}


@router.post("/apply_referral_code/", tags=["points", "referral"])
def apply_referral_code(
    referral_code: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    try:
        logging.info(
            f"Apply referral code request from {user_id} with code {referral_code}"
        )
        referral_manager.apply_referral_code(user_id, referral_code)
        return {"status": "success", "message": "Referral code applied successfully"}
    except ValueError as e:
        logging.error(f"Error in applying referral code for {user_id}. Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.post("/", response_model=UserResponse, tags=["user"])
def create_user(
    annonymous_uid: str | None = None,
    current_user=Depends(get_current_user),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(
        f"Create user request from {current_user['user_id']}, {current_user['email']}"
    )
    try:
        if annonymous_uid:
            logging.info(f"Replace user id {annonymous_uid} with {current_user['user_id']}")
            if annonymous_uid.startswith("$RCAnonymousID:"):
                logging.info("Performing replacement")
                subscription_manager.replace_user_id(annonymous_uid, current_user["user_id"])
    
        user = user_manager.add_user(
            UserModel(
                uid=current_user["user_id"],
                email=current_user["email"],
                display_name=current_user["display_name"],
                photo_url=current_user["photo_url"],
            )
        )
        return {"status": "success", "error": "", "user": user}
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error Registering user, {e}"
        ) from e


@router.put("/", response_model=UserResponse, tags=["user"])
def update_user(
    user_update: UserUpdate,
    current_user=Depends(get_current_user),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Update user request from {current_user['user_id']}")
    if not user_manager.user_exists(current_user["user_id"]):
        user = user_manager.add_user(
            UserModel(
                uid=current_user["user_id"],
                email=current_user["email"],
                display_name=current_user["display_name"],
                photo_url=current_user["photo_url"],
            )
        )

    user_update = user_update.model_dump(exclude_none=True)
    user_manager.update_user(current_user["user_id"], **user_update)
    user = user_manager.get_user_by_uid(current_user["user_id"])
    return {"status": "success", "error": "", "user": user}


@router.delete("/", response_model=DeleteUserResponse, tags=["user"])
def delete_user(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    logging.info(f"Delete user request from {user_id}")
    vector_ids = user_manager.get_all_vector_ids_for_user(user_id)
    knowledge_manager.delete_ids(vector_ids)
    user = user_manager.delete_user(user_id)
    conversation_manager.delete_all_conversations(user_id)
    subscription_manager.apply_or_default_subscription(user_id, update=True)
    if user == 0:
        logging.error(f"User not found {user_id}")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"status": "success", "error": "", "user": user}


@router.get("/", response_model=UserResponse, tags=["user"])
def get_user(
    current_user=Depends(get_current_user),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Get user request from {current_user['user_id']}")
    if user := user_manager.get_user_by_uid(current_user["user_id"]):
        return {"status": "success", "error": "", "user": user}

    user = user_manager.add_user(
        UserModel(
            uid=current_user["user_id"],
            email=current_user["email"],
            display_name=current_user["display_name"],
            photo_url=current_user["photo_url"],
        )
    )
    return {"status": "success", "error": "", "user": user}
