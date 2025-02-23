from pymongo import MongoClient
from pydantic import BaseModel
from typing import Optional

class UserUIDMapping(BaseModel):
    uid: str
    anonymous_ids: list[str]

class AnonymousUIDMapping:
    def __init__(self, mongo_uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def add_anonymous_id(self, uid: str, anonymous_id: str):
        self.collection.update_one(
            {'uid': uid},
            {'$addToSet': {'anonymous_ids': anonymous_id}},
            upsert=True
        )

    def get_uid_by_anonymous_id(self, anonymous_id: str) -> Optional[str]:
        result = self.collection.find_one({'anonymous_ids': anonymous_id})
        return result['uid'] if result else None

    def get_anonymous_ids_by_uid(self, uid: str) -> list[str]:
        result = self.collection.find_one({'uid': uid})
        return list(set(result['anonymous_ids'])) if result else None

if __name__ == '__main__':
    import os

    # Replace with your actual MongoDB URI and collection details
    mongo_uri = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/')
    db_name = 'test_db'
    collection_name = 'user_mappings'

    # Setup and clear any previous test data
    mapping = AnonymousUIDMapping(mongo_uri, db_name, collection_name)
    mapping.collection.delete_many({})

    # Test data
    uid = 'user123'
    anon_id1 = 'anon_a'
    anon_id2 = 'anon_b'

    # Test case 1: Add anonymous_id and verify
    mapping.add_anonymous_id(uid, anon_id1)
    assert mapping.get_anonymous_ids_by_uid(uid) == [anon_id1], "Test case 1 failed"

    # Test case 2: Add another anonymous_id and verify
    mapping.add_anonymous_id(uid, anon_id2)
    assert set(mapping.get_anonymous_ids_by_uid(uid)) == {anon_id1, anon_id2}, "Test case 2 failed"

    # Test case 3: Retrieve uid by anonymous_id
    assert mapping.get_uid_by_anonymous_id(anon_id1) == uid, "Test case 3 failed"
    assert mapping.get_uid_by_anonymous_id(anon_id2) == uid, "Test case 3 failed"

    # Test case 4: Non-existing anonymous_id should return None
    assert mapping.get_uid_by_anonymous_id('non_existent_id') is None, "Test case 4 failed"

    print("All tests passed.")
