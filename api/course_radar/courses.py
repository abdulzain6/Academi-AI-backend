from fastapi import APIRouter, Depends, HTTPException
from api.lib.database.purchases import SubscriptionType
from ..globals import course_manager, subscription_manager
from ..auth import get_user_id, verify_play_integrity



router = APIRouter()


@router.get("/")
def get_courses(
    page: int = 1,
    page_size: int = 10,
):
    courses, total = course_manager.get_courses(
        page=page, page_size=min(page_size, 30)
    )
    return {
        "courses" : [course.model_dump() for course in courses],
        "total" : total
    }
    
@router.get("/search")
def search_courses(
    query: str,
    page: int = 1,
    page_size: int = 10
):
    courses, total = course_manager.search_courses(
        page=page, page_size=min(page_size, 30), query_str=query
    )
    return {
        "courses" : [course.model_dump() for course in courses],
        "total" : total
    }