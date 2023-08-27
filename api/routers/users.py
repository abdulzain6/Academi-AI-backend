from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..auth import get_current_user
from ..globals import user_manager, knowledge_manager, collection_manager
from ..lib.database import UserModel

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
    
    class Config:
        extra = "forbid"
    

@router.get("/", response_model=UserResponse)
async def get_user(current_user=Depends(get_current_user)):
    if user := user_manager.get_user_by_uid(current_user["user_id"]):
        return {"status": "success", "error": "", "user": user}
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    

@router.post("/", response_model=UserResponse)
async def create_user(current_user=Depends(get_current_user)):
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
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error Registering user, {e}") from e

@router.put("/", response_model=UserResponse)
async def update_user(user_update: UserUpdate, current_user=Depends(get_current_user)):
    if not user_manager.user_exists(current_user["user_id"]):
        raise HTTPException(detail="User does not exist", status_code=404)
    user_update = user_update.model_dump()
    user_manager.update_user(current_user["user_id"], **user_update)
    user = user_manager.get_user_by_uid(current_user["user_id"])
    return {"status": "success", "error": "", "user": user}
    

@router.delete("/", response_model=DeleteUserResponse)
async def delete_user(current_user=Depends(get_current_user)):
    ids = user_manager.get_all_vector_ids_for_user(current_user["user_id"])
    for vectordb_collection, value in ids.items():
        knowledge_manager.delete_ids(vectordb_collection, value)
    user = user_manager.delete_user(current_user["user_id"])
    if user == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"status": "success", "error": "", "user": user}
    