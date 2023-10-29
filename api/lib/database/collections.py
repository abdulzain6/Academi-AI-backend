from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from .files import FileDBManager
from typing import List, Optional
from pydantic import BaseModel



class CollectionModel(BaseModel):
    user_uid: str
    name: str
    description: Optional[str] = None
    vectordb_collection_name: str
    number_of_files: Optional[int] = 0
    collection_uid: str


class CollectionDBManager:
    def __init__(self, connection_string: str, database_name: str, file_manager: FileDBManager = None) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]

        self.collection_collection: Collection = self.db["collections"]
        self.collection_collection.create_index("collection_uid", unique=True)
        self.collection_collection.create_index(
            [("name", 1), ("user_uid", 1)], unique=True
        )
        if not file_manager:
            self.file_manager = FileDBManager(connection_string, database_name, self)
        else:
            self.file_manager = file_manager
            
    def get_collection_name_by_uid(self, collection_uid: str) -> Optional[str]:
        """
        Retrieve the collection name by its UID.

        Parameters:
        - collection_uid (str): The unique identifier for the collection.

        Returns:
        - Optional[str]: The name of the collection if found, else None.
        """
        if doc := self.collection_collection.find_one(
            {"collection_uid": collection_uid}
        ):
            return doc["name"]
        return None

    def resolve_collection_uid(self, name: str, user_id: str) -> Optional[str]:
        if doc := self.collection_collection.find_one(
            {"name": name, "user_uid": user_id}
        ):
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
            self.collection_collection.insert_one(collection_model.model_dump())
            return collection_model
        else:
            raise ValueError("Collection already exists")

    def get_collection_by_name_and_user(
        self, name: str, user_id: str
    ) -> Optional[CollectionModel]:
        collection_data = self.collection_collection.find_one({"name": name})
        if not collection_data:
            return
        collection_data[
            "number_of_files"
        ] = self.file_manager.count_files_in_collection(user_id, name)
        return CollectionModel(**collection_data)

    def get_all_by_user(self, user_id: str) -> List[CollectionModel]:
        cursor = self.collection_collection.find({"user_uid": user_id})
        collections = []
        for doc in cursor:
            name = doc["name"]
            doc["number_of_files"] = self.file_manager.count_files_in_collection(
                user_id, name
            )
            collections.append(CollectionModel(**doc))
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

        result = self.collection_collection.update_one(
            {"collection_uid": collection_uid}, {"$set": kwargs}
        )
        return result.modified_count

    def delete_collection(self, user_id: str, collection_name: str) -> int:
        deleted_count = self.file_manager.delete_many_files(user_id, collection_name)
        result = self.collection_collection.delete_one({"name": collection_name})
        return result.deleted_count

    def delete_all(self, user_id: str) -> int:
        collections = self.get_all_by_user(user_id)
        total_deleted_count = 0
        for collection in collections:
            name = collection.name
            deleted_count = self.file_manager.delete_many_files(user_id, name)
            total_deleted_count += deleted_count
        result = self.collection_collection.delete_many({"user_uid": user_id})
        return result.deleted_count