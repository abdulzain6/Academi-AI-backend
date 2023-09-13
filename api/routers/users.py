from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..auth import get_current_user, get_user_id
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
    email: Optional[str]
    display_name: Optional[str]
    photo_url: Optional[str]
    
    

@router.get("/", response_model=UserResponse)
def get_user(user_id=Depends(get_user_id)):
    if user := user_manager.get_user_by_uid(user_id):
        return {"status": "success", "error": "", "user": user}
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
@router.post("/", response_model=UserResponse)
def create_user(current_user=Depends(get_current_user)):
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
def update_user(user_update: UserUpdate, user_id=Depends(get_user_id)):
    if not user_manager.user_exists(user_id):
        raise HTTPException(detail="User does not exist", status_code=404)
    user_update = user_update.model_dump()
    user_manager.update_user(user_id, **user_update)
    user = user_manager.get_user_by_uid(user_id)
    return {"status": "success", "error": "", "user": user}
    
@router.delete("/", response_model=DeleteUserResponse)
def delete_user(user_id=Depends(get_user_id)):
    collections = collection_manager.get_all_by_user(user_id)
    for collection in collections:
        if not knowledge_manager.delete_collection(collection.vectordb_collection_name):
            raise HTTPException(400, "ERROR DELETING COLLECTION")

    user = user_manager.delete_user(user_id)
    if user == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"status": "success", "error": "", "user": user}
    