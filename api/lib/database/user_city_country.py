from pymongo import MongoClient
from pydantic import BaseModel
from typing import Optional
from pymongo.collection import Collection

class UserLocation(BaseModel):
    user_id: str
    city: str
    country: str

class UserLocationDB:
    def __init__(self, connection_string: str, db_name: str):
        self.client = MongoClient(connection_string)
        self.db = self.client[db_name]
        self.collection: Collection = self.db['locations']
        self.collection.create_index('user_id', unique=True)

    def create_location(self, user_location: UserLocation):
        return self.collection.insert_one(user_location.model_dump())

    def get_location(self, user_id: str) -> Optional[UserLocation]:
        result = self.collection.find_one({'user_id': user_id}, projection={'_id': 0})
        return UserLocation(**result) if result else None

    def update_location(self, user_location: UserLocation):
        return self.collection.update_one(
            {'user_id': user_location.user_id},
            {'$set': user_location.model_dump()},
            upsert=True
        )

    def delete_location(self, user_id: str):
        return self.collection.delete_one({'user_id': user_id})

    def bulk_create_locations(self, user_locations: list[UserLocation]):
        return self.collection.insert_many([ul.model_dump() for ul in user_locations])

    def bulk_update_locations(self, user_locations: list[UserLocation]):
        operations = [
            {
                'update_one': {
                    'filter': {'user_id': ul.user_id},
                    'update': {'$set': ul.model_dump()},
                    'upsert': True
                }
            }
            for ul in user_locations
        ]
        return self.collection.bulk_write(operations)

    def __del__(self):
        self.client.close()