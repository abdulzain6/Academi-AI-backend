import logging
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import get_user_id, verify_play_integrity
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
def create_collection(
    collection: CollectionCreate,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        if collection_manager.collection_exists(collection.name, user_id):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Collection with this name already exists"
            )

        uid = str(uuid.uuid4())  # Generate a new UID for the collection
        added_collection = collection_manager.add_collection(
            CollectionModel(
                user_uid=user_id,
                name=collection.name,
                description=collection.description,
                collection_uid=uid,
                vectordb_collection_name=f"{user_id}_{uid}",
            )
        )
        return StatusCollectionResponse(collection=added_collection)
    except Exception as e:
        logging.error(f"Error making collection, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error making collection, {e}"
        ) from e


@router.delete("/", response_model=StatusCollectionResponse)
def delete_collections(
    collection: CollectionDelete,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if existing_collection := collection_manager.get_collection_by_name_and_user(
        collection.name, user_id
    ):
        knowledge_manager.delete_collection(
            existing_collection.vectordb_collection_name
        )
        return (
            StatusCollectionResponse(collection=existing_collection)
            if (
                collection := collection_manager.delete_collection(
                    user_id, collection.name
                )
            )
            else StatusCollectionResponse(
                collection=existing_collection, status="error"
            )
        )
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Collection with this name does not exist"
        )


@router.put("/{collection_name}", response_model=UpdateCollectionResponse)
def update_collection(
    collection_name: str,
    collection_update: CollectionUpdate,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        if collection_update.name and collection_manager.collection_exists(
            collection_update.name, user_id
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Collection name already exists"
            )

        to_update = collection_update.model_dump()
        updated_rows = collection_manager.update_collection(
            user_id=user_id, collection_name=collection_name, **to_update
        )
        if updated_rows == 0:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "No collection found to update"
            )
        return UpdateCollectionResponse(updated_rows=updated_rows)
    except Exception as e:
        logging.error(f"Error updating collection, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Error updating collection"
        ) from e


@router.get("/{collection_name}", response_model=StatusCollectionResponse)
def get_collection_by_name(
    collection_name: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        if collection := collection_manager.get_collection_by_name_and_user(
            name=collection_name, user_id=user_id
        ):
            return StatusCollectionResponse(collection=collection)
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found")
    except Exception as e:
        logging.error(f"Error getting collection, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error getting collection, {e}"
        ) from e


@router.get("/", response_model=MultipleCollectionResponse)
def get_all_collections(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    try:
        collections = collection_manager.get_all_by_user(user_id=user_id)
        return MultipleCollectionResponse(collections=collections)
    except Exception as e:
        logging.error(f"Error getting collections, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error getting collections, {e}"
        ) from e


@router.delete("/all", response_model=DeleteCollectionResponse)
def delete_all_collections(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    try:
        collections = collection_manager.get_all_by_user(user_id)
        for collection in collections:
            if not knowledge_manager.delete_collection(
                collection.vectordb_collection_name
            ):
                raise HTTPException(400, "ERROR DELETING COLLECTION")

        deleted_count = collection_manager.delete_all(user_id=user_id)
        return DeleteCollectionResponse(deleted_rows=deleted_count)
    except Exception as e:
        logging.error(f"Error deleting all collections, {e}")
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Error deleting all collections, {e}"
        ) from e
