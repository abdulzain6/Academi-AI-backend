from fastapi import APIRouter, Depends
from ..auth import get_user_id, verify_play_integrity
from ..globals import (
    FEATURE_PRICING,
)


router = APIRouter()

@router.get("/feature_pricing", tags=["pricing", "info"])
def get_number_of_ads_watched(
    user_id: str = Depends(get_user_id),
    play_integrity_verified: None = Depends(verify_play_integrity),
) -> dict:
    return FEATURE_PRICING