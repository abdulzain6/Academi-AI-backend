import contextlib
import json
import logging, redis
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError
from .collections import CollectionDBManager
from .cache_manager import CacheProtocol

class UserModel(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    referred_by: Optional[str] = None
    referred_by: Optional[str] = None


class UserDBManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_manager: CollectionDBManager = None,
        cache_manager: CacheProtocol = None
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.user_collection: Collection = self.db["users"]
        self.user_collection.create_index("uid", unique=True)
        if not collection_manager:
            self.collection_manager = CollectionDBManager(
                connection_string, database_name
            )
        else:
            self.collection_manager = collection_manager
            
        self.cache_manager = cache_manager
            
    def get_all_vector_ids_for_user(self, user_id: str) -> Dict[str, List[str]]:
        vector_ids_per_collection = {}
        user_collections = self.collection_manager.get_all_by_user(user_id)
        for collection in user_collections:
            collection_name = collection.name
            vectordb_collection_name = collection.vectordb_collection_name
            collection_vector_ids = self.collection_manager.get_all_vector_ids(
                user_id, collection_name
            )
            vector_ids_per_collection[vectordb_collection_name] = collection_vector_ids
        return vector_ids_per_collection

    def add_user(self, user_model: UserModel) -> UserModel:
        if self.user_exists(user_model.uid):
            raise ValueError("User already exists")
        self.user_collection.insert_one(user_model.model_dump())
        self.cache_manager.delete("all_users")
        return user_model
    
    def get_user_by_uid(self, uid: str) -> Optional[UserModel]:
        cache_key = f"user:{uid}"
        if cached_data := self.cache_manager.get(cache_key):
            return UserModel(**cached_data)

        if user_data := self.user_collection.find_one({"uid": uid}):
            self.cache_manager.set(cache_key, user_data)
            return UserModel(**user_data)

        return None

    def user_exists(self, uid: str) -> bool:
        return self.user_collection.count_documents({"uid": uid}, limit=1) > 0

    def get_all(self) -> List[UserModel]:
        cache_key = "all_users"
        if cached_data := self.cache_manager.get(cache_key):
            return [UserModel(**doc) for doc in cached_data]

        all_users = list(self.user_collection.find({}))
        self.cache_manager.set(cache_key, all_users)

        return [UserModel(**doc) for doc in all_users]

    def insert_many(self, rows: List[UserModel]) -> None:
        try:
            self.user_collection.insert_many(
                [user_model.model_dump() for user_model in rows], ordered=False
            )
        except BulkWriteError as bwe:
            logging.error(bwe.details)

    def update_user(self, uid: str, **kwargs: Dict[str, Any]) -> int:
        if "uid" in kwargs:
            raise ValueError("Changing 'uid' is not allowed.")
        result = self.user_collection.update_one({"uid": uid}, {"$set": kwargs})
        self.cache_manager.delete(f"user:{uid}")
        self.cache_manager.delete("all_users")
        return result.modified_count

    def delete_user(self, uid: str) -> int:
        if not self.user_exists(uid):
            return 0
        self.collection_manager.delete_all(uid)
        self.user_collection.delete_one({"uid": uid})
        self.cache_manager.delete(f"user:{uid}")
        self.cache_manager.delete("all_users")
        return 1
