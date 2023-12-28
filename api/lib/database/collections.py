import logging
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
        vector_ids = [vector_id for file in all_files for vector_id in file.vector_ids]
        return vector_ids

    def add_collection(self, collection_model: CollectionModel) -> CollectionModel:
        if not self.collection_exists(collection_model.name, collection_model.user_uid):
            self.collection_collection.insert_one(collection_model.model_dump())
            return collection_model
        else:
            raise ValueError("Subject already exists")

    def get_collection_by_name_and_user(self, name: str, user_id: str) -> Optional[CollectionModel]:
        pipeline = [
            {"$match": {"name": name, "user_uid": user_id}},
            {
                "$lookup": {
                    "from": "files",  # Ensure this matches your files collection name
                    "localField": "collection_uid",  # This field should exist in your collections documents
                    "foreignField": "collection_uid",  # This field should exist in your files documents
                    "as": "files",
                }
            },
            {"$addFields": {"number_of_files": {"$size": "$files"}}},
            {"$project": {"files": 0}},  # Exclude the "files" field from the results
        ]

        try:
            collection_data = next(self.collection_collection.aggregate(pipeline))
        except StopIteration:
            return None

        return CollectionModel(**collection_data)
        
    def get_all_files_for_user_as_string(self, user_id: str) -> str:
        pipeline = [
            {"$match": {"user_uid": user_id}},
            {
                "$lookup": {
                    "from": self.file_manager.file_collection.name,
                    "localField": "collection_uid",
                    "foreignField": "collection_uid",
                    "as": "files",
                }
            },
            {
                "$project": {
                    "name": "$name",  # Project the name field
                    "description": "$description",  # Project the description field
                    "files": {
                        "$map": {
                            "input": "$files",
                            "as": "file",
                            "in": {
                                "collection_name": "$$file.collection_name",
                                "filename": "$$file.filename",
                                "friendly_filename": "$$file.friendly_filename",
                                "description": "$$file.description",
                                "filetype": "$$file.filetype",
                            }
                        }
                    }
                }
            }
        ]


        try:
            data = list(self.collection_collection.aggregate(pipeline))
            output_string = ""
            if not data:
                return "No subjects or files found, You can create a subject for the user."
            for subject in data:
                subject_name = subject['name']
                output_string += f"Subject name: '{subject_name}'\nFiles:\n"
                for file in subject['files']:
                    output_string += f"- Filename: '{file['friendly_filename']}' Filetype: '({file.get('filetype', 'No type')})' Description: '{file.get('description', 'No desc')}')\n"
                if not subject['files']:
                    output_string += f"- This subject has no files, ask the user to upload a file in the app or help with your knowledge. You can also create files from youtube or web links. Documents have to be added manually "
                output_string += "\n"  # Add extra newline for separation between subjects

            return output_string
        except Exception as e:
            print(f"Error occurred: {e} {data}")
            return "An error occurred while fetching data."
        
    def get_all_by_user(self, user_id: str, dict: bool = False) -> List[CollectionModel] | List[Dict]:
        pipeline = [
            {"$match": {"user_uid": user_id}},
            {
                "$lookup": {
                    "from": "files",  # Make sure this is the correct name of the files collection
                    "localField": "collection_uid",  # Verify this field exists in the collections
                    "foreignField": "collection_uid",  # Verify this field exists in the files
                    "as": "files",
                }
            },
            {"$addFields": {"number_of_files": {"$size": "$files"}}},
            {"$project": {"files": 0}},  # Exclude the "files" field from the results
        ]
        results = list(self.collection_collection.aggregate(pipeline))
        if not dict:
            return [CollectionModel(**doc) for doc in results]
        else:
            return [CollectionModel(**doc).model_dump() for doc in results]

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
        collection_uid = self.resolve_collection_uid(collection_name, user_id)
        deleted_count = self.file_manager.delete_many_files(user_id, collection_name)
        result = self.collection_collection.delete_one({"collection_uid": collection_uid})
        return result.deleted_count

    def delete_all(self, user_id: str) -> int:
        collections = self.get_all_by_user(user_id)
        total_deleted_count = 0
        for collection in collections:
            name = collection.name
            deleted_count = self.file_manager.delete_many_files(user_id, name)
            total_deleted_count += deleted_count

        result = self.collection_collection.delete_many({"user_uid": user_id})
        logging.info(f"Deleted {result.deleted_count} files")
        return result.deleted_count
