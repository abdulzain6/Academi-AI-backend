import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import get_current_user
from ..globals import collection_manager, knowledge_manager, user_manager
from fastapi import Depends, HTTPException, status
from ..lib.database import CollectionModel

router = APIRouter()


class CollectionUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]

class CollectionCreate(BaseModel):
    name: str
    description: str
    
class CollectionDelete(BaseModel):
    name: str
    
class StatusCollectionResponse(BaseModel):
    collection: CollectionModel
    status: str = "success"
    
class UpdateCollectionResponse(BaseModel):
    updated_rows: int = 0
    status: str = "success"
    
class DeleteCollectionResponse(BaseModel):
    deleted_rows: int = 0
    status: str = "success"

class MultipleCollectionResponse(BaseModel):
    collections: list[CollectionModel]
    status: str = "success"


@router.post("/", response_model=StatusCollectionResponse)
async def create_collection(collection: CollectionCreate, current_user=Depends(get_current_user)):
    try:
        logging.info(current_user)

        if collection_manager.collection_exists(
            collection.name, current_user["user_id"]
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Collection with this name already exists")

        added_collection = collection_manager.add_collection(
            CollectionModel(
                user_uid=current_user["user_id"],
                name=collection.name,
                description=collection.description,
                vectordb_collection_name=f"{current_user['user_id']}_{collection.name}"
            )
        )
        return StatusCollectionResponse(collection=added_collection)
    except Exception as e:
        logging.error(f"Error making collection, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error making collection, {e}") from e

    
@router.delete("/", response_model=StatusCollectionResponse)
async def delete_collections(collection: CollectionDelete, current_user=Depends(get_current_user)):
    logging.info(current_user)
    if existing_collection := collection_manager.get_collection_by_name_and_user(
        collection.name, current_user["user_id"]
    ):
        vector_ids = collection_manager.get_all_vector_ids(current_user["user_id"], existing_collection.name)
        knowledge_manager.delete_ids(existing_collection.vectordb_collection_name, vector_ids)
        return (
            StatusCollectionResponse(collection=existing_collection)
            if (
                collection := collection_manager.delete_collection(
                    current_user["user_id"], collection.name
                )
            )
            else StatusCollectionResponse(collection=existing_collection, status="error")
        )
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Collection with this name does not exist")


@router.put("/{collection_name}", response_model=UpdateCollectionResponse)
async def update_collection(collection_name: str, collection_update: CollectionUpdate, current_user=Depends(get_current_user)):
    try:
        logging.info(current_user)

        if collection_update.name and collection_manager.collection_exists(
                        collection_update.name, current_user["user_id"]
                    ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Collection name already exists")

        to_update = collection_update.model_dump()
        
        if collection_update.name:
            vectordb_collection_name = f"{current_user['user_id']}_{collection_update.name}"
            to_update["vectordb_collection_name"] = vectordb_collection_name
            
        updated_rows = collection_manager.update_collection(
            user_id=current_user["user_id"],
            collection_name=collection_name,
            **to_update
        )
        if updated_rows == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No collection found to update")
        return UpdateCollectionResponse(updated_rows=updated_rows)
    except Exception as e:
        logging.error(f"Error updating collection, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, "Error updating collection") from e


@router.get("/{collection_name}", response_model=StatusCollectionResponse)
async def get_collection_by_name(collection_name: str, current_user=Depends(get_current_user)):
    try:
        logging.info(current_user)
        if collection := collection_manager.get_collection_by_name_and_user(
            name=collection_name, user_id=current_user["user_id"]
        ):
            return StatusCollectionResponse(collection=collection)
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    except Exception as e:
        logging.error(f"Error getting collection, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error getting collection, {e}") from e


@router.get("/", response_model=MultipleCollectionResponse)
async def get_all_collections(current_user=Depends(get_current_user)):
    try:
        logging.info(current_user)
        collections = collection_manager.get_all_by_user(
            user_id=current_user["user_id"]
        )
        return MultipleCollectionResponse(collections=collections)
    except Exception as e:
        logging.error(f"Error getting collections, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error getting collections, {e}") from e


@router.delete("/all", response_model=DeleteCollectionResponse)
async def delete_all_collections(current_user=Depends(get_current_user)):
    try:
        logging.info(current_user)
        
        ids = user_manager.get_all_vector_ids_for_user(current_user["user_id"])
        for vectordb_collection, value in ids.items():
            knowledge_manager.delete_ids(vectordb_collection, value)
            
        deleted_count = collection_manager.delete_all(
            user_id=current_user["user_id"]
        )
        return DeleteCollectionResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting all collections, {e}")
        raise HTTPException(status.HTTP_409_CONFLICT, f"Error deleting all collections, {e}") from e
