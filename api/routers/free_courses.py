from fastapi import APIRouter, Depends, HTTPException
from api.lib.database.purchases import SubscriptionType
from ..globals import course_manager, subscription_manager
from ..auth import get_user_id, verify_play_integrity



router = APIRouter()


@router.get("/")
def get_courses(
    page: int = 1,
    page_size: int = 10,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    courses, total = course_manager.get_courses(
        page=page, page_size=max(page_size, 30)
    )
    return {
        "courses" : [{"is_premium" : True if (course.actual_price_usd - course.sale_price_usd) >= 100  else False, **course.model_dump(exclude=["url"])} for course in courses],
        "total" : total
    }
    
@router.get("/search")
def search_courses(
    query: str,
    page: int = 1,
    page_size: int = 10,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    courses, total = course_manager.search_courses(
        page=page, page_size=max(page_size, 30), query_str=query
    )
    return {
        "courses" : [course.model_dump(exclude=["url"]) for course in courses],
        "total" : total
    }
    
@router.get("/coupon")
def get_full_coupon_url(
    url: str,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    course = course_manager.get_course_by_clean_url(
       clean_url=url
    )
    if not course:
        raise HTTPException(400, detail="Course not available")
    
    if (course.actual_price_usd - course.sale_price_usd) >= 100:
        if subscription_manager.get_subscription_type(user_id) in {SubscriptionType.FREE}:
            raise HTTPException(status_code=400, detail="You must be subscribed to to access this course.")    
 
    return course