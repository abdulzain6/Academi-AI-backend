from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..auth import get_current_user, get_user_id, verify_play_integrity
from ..globals import (
    user_manager,
    knowledge_manager,
    collection_manager,
    user_points_manager,
    DEFAULT_POINTS_INCREMENT,
    referral_manager
)
from ..lib.database import UserModel, UserPoints

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
    email: Optional[str]
    display_name: Optional[str]
    photo_url: Optional[str]



@router.post("/increment_points/", tags=["points", "ads"])
def increment_points(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity)
) -> dict:
    if not user_points_manager.can_increment_from_ad(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: Max {user_points_manager.max_ads_per_hour} ad watches per hour."
        )

    modified_count = user_points_manager.increment_user_points(user_id, DEFAULT_POINTS_INCREMENT)
    if modified_count > 0:
        return {
            "status": "success",
            "message": f"Incremented points by {DEFAULT_POINTS_INCREMENT}",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to increment points."
        )

@router.get("/is_daily_bonus_claimed/", tags=["points", "daily bonus"])
def is_daily_bonus_claimed(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    is_claimed = user_points_manager.is_daily_bonus_claimed(user_id)
    return {"status": "success", "is_claimed": is_claimed}


@router.get("/points", response_model=UserPoints, tags=["points", "ads"])
def get_user_points(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    if user_points := user_points_manager.get_user_points(user_id):
        return user_points.model_dump()
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")


@router.post("/claim_daily_bonus/", tags=["points", "daily bonus"])
def claim_daily_bonus(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    bonus_points = user_points_manager.claim_daily_bonus(user_id)
    if bonus_points > 0:
        return {"status": "success", "message": f"Claimed {bonus_points} bonus points"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to claim daily bonus, Might be already claimed",
        )


@router.get("/streak_day/", tags=["points", "daily bonus"])
def get_streak_day(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    streak_day = user_points_manager.get_streak_day(user_id)
    return {"status": "success", "streak_day": streak_day}



@router.get("/get_referral_code/", tags=["points", "referral"])
def get_referral_code(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    return {"status": "success", "referral_code": user_id}


@router.post("/apply_referral_code/", tags=["points", "referral"])
def apply_referral_code(
    referral_code: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    try:
        referral_manager.apply_referral_code(user_id, referral_code)
        return {"status": "success", "message": "Referral code applied successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e





@router.post("/", response_model=UserResponse, tags=["user"])
def create_user(
    current_user=Depends(get_current_user),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
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
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if not user_manager.user_exists(user_id):
        raise HTTPException(detail="User does not exist", status_code=404)
    user_update = user_update.model_dump()
    user_manager.update_user(user_id, **user_update)
    user = user_manager.get_user_by_uid(user_id)
    return {"status": "success", "error": "", "user": user}


@router.delete("/", response_model=DeleteUserResponse, tags=["user"])
def delete_user(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    collections = collection_manager.get_all_by_user(user_id)
    for collection in collections:
        if not knowledge_manager.delete_collection(collection.vectordb_collection_name):
            raise HTTPException(400, "ERROR DELETING COLLECTION")

    user = user_manager.delete_user(user_id)
    if user == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"status": "success", "error": "", "user": user}

@router.get("/", response_model=UserResponse, tags=["user"])
def get_user(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    if user := user_manager.get_user_by_uid(user_id):
        return {"status": "success", "error": "", "user": user}
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")