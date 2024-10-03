from pymongo import MongoClient
from typing import Optional
import uuid

class UUIDMapping:
    def __init__(self, mongo_uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def create_mapping(self, user_id: str) -> str:
        uuid_id = str(uuid.uuid4())  # Generate a unique UID
        document = {
            "uuid_id": uuid_id,
            "uid": user_id
        }
        self.collection.insert_one(document)
        return uuid_id

    def get_uid(self, uuid_id: str) -> Optional[str]:
        result = self.collection.find_one({"uuid_id": uuid_id})
        if result:
            return result["uid"]
        return None

    def get_uuid(self, uid: str) -> Optional[str]:
        result = self.collection.find_one({"uid": uid})
        if result:
            return result["uuid_id"]
        return None

    def delete_mapping(self, uuid_id: str) -> bool:
        result = self.collection.delete_one({"uuid_id": uuid_id})
        return result.deleted_count > 0

    def close(self):
        self.client.close()
