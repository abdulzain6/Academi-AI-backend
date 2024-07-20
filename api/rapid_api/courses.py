from fastapi import APIRouter, Depends
from ..globals import course_manager
from .auth import verify_rapidapi_key
import logging


router = APIRouter()

@router.get("/")
def get_courses(
    page: int = 1,
    page_size: int = 10,
    _ = Depends(verify_rapidapi_key)
):
    logging.info(f"Rapidapi request on get courses. Page : {page}, Size: {page_size}")
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
    page_size: int = 10,
    _ = Depends(verify_rapidapi_key)
):
    logging.info(f"Rapidapi request on search courses. Query: {query}, Page : {page}, Size: {page_size}")

    courses, total = course_manager.search_courses(
        page=page, page_size=min(page_size, 30), query_str=query
    )
    return {
        "courses" : [course.model_dump() for course in courses],
        "total" : total
    }