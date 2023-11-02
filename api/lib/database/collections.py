from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from .files import FileDBManager
from typing import List, Optional
from pydantic import BaseModel
from .cache_manager import CacheProtocol
import redis


class CollectionModel(BaseModel):
    user_uid: str
    name: str
    description: Optional[str] = None
    vectordb_collection_name: str
    number_of_files: Optional[int] = 0
    collection_uid: str


class CollectionDBManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        file_manager: FileDBManager = None,
        cache_manager: CacheProtocol = None,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]

        self.collection_collection: Collection = self.db["collections"]
        self.collection_collection.create_index("collection_uid", unique=True)
        self.collection_collection.create_index(
            [("name", 1), ("user_uid", 1)], unique=True
        )
        if not file_manager:
            self.file_manager = FileDBManager(connection_string, database_name, self, cache_manager)
        else:
            self.file_manager = file_manager

        self.cache_manager = cache_manager

    def get_collection_name_by_uid(self, collection_uid: str) -> Optional[str]:
        cache_key = f"collection_name:{collection_uid}"
        if cached_data := self.cache_manager.get(cache_key):
            return cached_data

        if doc := self.collection_collection.find_one(
            {"collection_uid": collection_uid}
        ):
            self.cache_manager.set(cache_key, doc["name"])
            return doc["name"]

        return None

    def resolve_collection_uid(self, name: str, user_id: str) -> Optional[str]:
        cache_key = f"collection_uid:{name}:{user_id}"
        if cached_data := self.cache_manager.get(cache_key):
            return cached_data

        if doc := self.collection_collection.find_one(
            {"name": name, "user_uid": user_id}
        ):
            self.cache_manager.set(cache_key, doc["collection_uid"])
            return doc["collection_uid"]

        return None

    def collection_exists(self, name: str, user_id: str) -> bool:
        return bool(
            self.collection_collection.find_one(
                {"name": name, "user_uid": user_id}, {"_id": 1}
            )
        )

    def get_all_vector_ids(self, user_id: str, collection_name: str) -> List[str]:
        all_files = self.file_manager.get_all_files(user_id, collection_name)
        return [file.vector_ids for file in all_files]

    def add_collection(self, collection_model: CollectionModel) -> CollectionModel:
        if not self.collection_exists(collection_model.name, collection_model.user_uid):
            cache_key = f"all_collections_by_user:{collection_model.user_uid}"
            self.cache_manager.delete(cache_key)
            self.collection_collection.insert_one(collection_model.model_dump())
            return collection_model
        else:
            raise ValueError("Collection already exists")

    def get_collection_by_name_and_user(
        self, name: str, user_id: str
    ) -> Optional[CollectionModel]:
        cache_key = f"collection_by_name_and_user:{name}:{user_id}"
        if cached_data := self.cache_manager.get(cache_key):
            return CollectionModel(**cached_data)

        if collection_data := self.collection_collection.find_one({"name": name}):
            collection_data[
                "number_of_files"
            ] = self.file_manager.count_files_in_collection(user_id, name)
            self.cache_manager.set(cache_key, collection_data)
            return CollectionModel(**collection_data)

        return None

    def get_all_by_user(self, user_id: str) -> List[CollectionModel]:
        cache_key = f"all_collections_by_user:{user_id}"
        if cached_data := self.cache_manager.get(cache_key):
            collections = []
            for data in cached_data:
                data["number_of_files"] = self.file_manager.count_files_in_collection(
                    user_id, data["name"]
                )
                collections.append(CollectionModel(**data))
            return collections

        cursor = self.collection_collection.find({"user_uid": user_id})
        essential_collections = []
        collections = []
        for doc in cursor:
            essential_doc = {key: doc[key] for key in doc if key != "number_of_files"}
            essential_collections.append(essential_doc)
            doc["number_of_files"] = self.file_manager.count_files_in_collection(
                user_id, essential_doc["name"]
            )
            collections.append(CollectionModel(**doc))

        self.cache_manager.set(cache_key, essential_collections)
        return collections

    def update_collection(
        self, user_id: str, collection_name: str, **kwargs: Dict
    ) -> int:
        collection_uid = self.resolve_collection_uid(collection_name, user_id)
        if not collection_uid:
            return 0
        if "name" in kwargs:
            new_name = kwargs["name"]
            if self.collection_exists(new_name, user_id):
                raise ValueError("A collection with this new name already exists")

        self.clear_cache(collection_name, user_id, collection_uid)
        result = self.collection_collection.update_one(
            {"collection_uid": collection_uid}, {"$set": kwargs}
        )
        return result.modified_count

    def delete_collection(self, user_id: str, collection_name: str) -> int:
        collection_uid = self.resolve_collection_uid(collection_name, user_id)
        deleted_count = self.file_manager.delete_many_files(user_id, collection_name)
        self.clear_cache(collection_name, user_id, collection_uid)
        result = self.collection_collection.delete_one({"name": collection_name})
        return result.deleted_count

    def clear_cache(self, collection_name, user_id, collection_uid):
        self.cache_manager.delete(
            f"collection_by_name_and_user:{collection_name}:{user_id}"
        )
        self.cache_manager.delete(f"all_collections_by_user:{user_id}")
        self.cache_manager.delete(f"collection_name:{collection_uid}")
        self.cache_manager.delete(f"collection_uid:{collection_name}:{user_id}")

    def delete_all(self, user_id: str) -> int:
        self.cache_manager.delete(f"all_collections_by_user:{user_id}")
        collections = self.get_all_by_user(user_id)
        total_deleted_count = 0
        for collection in collections:
            self.clear_cache(
                collection_name=collection.name,
                user_id=user_id,
                collection_uid=self.resolve_collection_uid(collection.name, user_id),
            )
            name = collection.name
            deleted_count = self.file_manager.delete_many_files(user_id, name)
            total_deleted_count += deleted_count

        result = self.collection_collection.delete_many({"user_uid": user_id})
        return result.deleted_count
