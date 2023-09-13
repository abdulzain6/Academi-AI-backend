from typing import Any, Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError
from gridfs import GridFS, NoFile
from .models import UserModel, CollectionModel, FileModel, Conversation, LatestConversation, MessagePair, UserLatestConversations

import uuid
import unittest

class UserDBManager:
    def __init__(self, connection_string: str, database_name: str) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.user_collection: Collection = self.db["users"]
        self.user_collection.create_index("uid", unique=True)
        self.collection_manager = CollectionDBManager(connection_string, database_name)

    def get_all_vector_ids_for_user(self, user_id: str) -> Dict[str, List[str]]:
        vector_ids_per_collection = {}
        user_collections = self.collection_manager.get_all_by_user(user_id)
        for collection in user_collections:
            collection_name = collection.name
            vectordb_collection_name = collection.vectordb_collection_name
            collection_vector_ids = self.collection_manager.get_all_vector_ids(user_id, collection_name)
            vector_ids_per_collection[vectordb_collection_name] = collection_vector_ids
        return vector_ids_per_collection

    def add_user(self, user_model: UserModel) -> UserModel:
        if self.user_exists(user_model.uid):
            raise ValueError("User already exists")
        self.user_collection.insert_one(user_model.model_dump())
        return user_model

    def get_user_by_uid(self, uid: str) -> Optional[UserModel]:
        user_data = self.user_collection.find_one({"uid": uid})
        return UserModel(**user_data) if user_data else None

    def user_exists(self, uid: str) -> bool:
        return self.user_collection.count_documents({"uid": uid}, limit=1) > 0

    def get_all(self) -> List[UserModel]:
        return [UserModel(**doc) for doc in self.user_collection.find({})]

    def insert_many(self, rows: List[UserModel]) -> None:
        try:
            self.user_collection.insert_many([user_model.model_dump() for user_model in rows], ordered=False)
        except BulkWriteError as bwe:
            print(bwe.details)

    def update_user(self, uid: str, **kwargs: dict) -> int:
        if 'uid' in kwargs:
            raise ValueError("Changing 'uid' is not allowed.")
        
        result = self.user_collection.update_one({"uid": uid}, {"$set": kwargs})
        return result.modified_count

    def delete_user(self, uid: str) -> int:
        if not self.user_exists(uid):
            return 0
        self.collection_manager.delete_all(uid)
        self.user_collection.delete_one({"uid": uid})
        return 1
    

class CollectionDBManager:
    def __init__(self, connection_string: str, database_name: str) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        
        self.collection_collection: Collection = self.db["collections"]        
        self.collection_collection.create_index("collection_uid", unique=True)
        self.collection_collection.create_index([("name", 1), ("user_uid", 1)], unique=True)
        
        self.file_manager = FileDBManager(connection_string, database_name, self)

    def resolve_collection_uid(self, name: str, user_id: str) -> Optional[str]:
        if doc := self.collection_collection.find_one(
            {"name": name, "user_uid": user_id}
        ):
            return doc['collection_uid']
        return None

    def collection_exists(self, name: str, user_id: str) -> bool:
        return bool(self.collection_collection.find_one({"name": name, "user_uid": user_id}, {"_id": 1}))

    def get_all_vector_ids(self, user_id: str, collection_name: str) -> List[str]:
        all_files = self.file_manager.get_all_files(user_id, collection_name)
        return [file.vector_ids for file in all_files]

    def add_collection(self, collection_model: CollectionModel) -> CollectionModel:
        if not self.collection_exists(collection_model.name, collection_model.user_uid):
            self.collection_collection.insert_one(collection_model.model_dump())
            return collection_model
        else:
            raise ValueError("Collection already exists")

    def get_collection_by_name_and_user(self, name: str, user_id: str) -> Optional[CollectionModel]:
        collection_data = self.collection_collection.find_one({"name": name})
        if not collection_data:
            return
        collection_data['number_of_files'] = self.file_manager.count_files_in_collection(user_id, name)
        return CollectionModel(**collection_data)

    def get_all_by_user(self, user_id: str) -> List[CollectionModel]:
        cursor = self.collection_collection.find({"user_uid": user_id})
        collections = []
        for doc in cursor:
            name = doc['name']
            doc['number_of_files'] = self.file_manager.count_files_in_collection(user_id, name)
            collections.append(CollectionModel(**doc))
        return collections

    def update_collection(self, user_id: str, collection_name: str, **kwargs: Dict) -> int:
        collection_uid = self.resolve_collection_uid(collection_name, user_id)
        if not collection_uid:
            return 0
        if 'name' in kwargs:
            new_name = kwargs['name']
            if self.collection_exists(new_name, user_id):
                raise ValueError("A collection with this new name already exists")
        
        result = self.collection_collection.update_one({"collection_uid": collection_uid}, {"$set": kwargs})
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
    

class FileDBManager:
    def __init__(self, connection_string: str, database_name: str, collection_manager: CollectionDBManager) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.collection_manager = collection_manager
        self.file_collection: Collection = self.db["files"]
        self.fs = GridFS(self.db)
        
        # Create unique index
        self.file_collection.create_index(
            [("user_id", 1), ("collection_uid", 1), ("filename", 1)], 
            unique=True
        )
        
    def resolve_collection_uid(self, user_id: str, collection_name: str) -> str:
        return self.collection_manager.resolve_collection_uid(collection_name, user_id)

    def add_file(self, file_model: FileModel) -> FileModel:
        collection_uid = self.resolve_collection_uid(file_model.user_id, file_model.collection_name)
        if self.file_exists(file_model.user_id, collection_uid, file_model.filename):
            raise ValueError("File already exists")
        
        file_id = self.fs.put(file_model.file_bytes, filename=file_model.filename)
        file_data = file_model.model_dump(exclude={"file_bytes"})
        file_data["file_id"] = file_id
        file_data["collection_uid"] = collection_uid  # Use collection_uid
        self.file_collection.insert_one(file_data)
        
        return file_model

    def get_file_by_name(self, user_id: str, collection_name: str, filename: str, bytes: bool = False) -> Optional[FileModel]:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        if file_data := self.file_collection.find_one(
            {
                "user_id": user_id,
                "collection_uid": collection_uid,
                "filename": filename,
            }
        ):
            if bytes:
                try:
                    file_data["file_bytes"] = self.fs.get(file_data["file_id"]).read()
                except NoFile:
                    file_data["file_bytes"] = b""
            return FileModel(**file_data)

        return None

    def file_exists(self, user_id: str, collection_uid: str, filename: str) -> bool:
        return self.file_collection.count_documents({
            "user_id": user_id,
            "collection_uid": collection_uid,
            "filename": filename
        }, limit=1) > 0

    def update_file(self, user_id: str, collection_name: str, old_filename: str, **kwargs: Dict[str, any]) -> int:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        if 'user_id' in kwargs or 'collection_uid' in kwargs:
            raise ValueError("Changing 'user_id' or 'collection_uid' is not allowed.")
       
        new_filename = kwargs.get("filename", old_filename)
        if new_filename != old_filename and self.file_exists(user_id, collection_uid, new_filename):
            raise ValueError(f"A file with the name {new_filename} already exists in the collection.")
        
        file_data = self.file_collection.find_one({
            "user_id": user_id,
            "collection_uid": collection_uid,
            "filename": old_filename
        })
        if not file_data:
            return 0  # File not found
        
        if 'file_bytes' in kwargs:
            self.fs.delete(file_data["file_id"])
            file_id = self.fs.put(kwargs['file_bytes'], filename=new_filename)
            kwargs['file_id'] = file_id
            del kwargs['file_bytes']

        result = self.file_collection.update_one({
            "user_id": user_id,
            "collection_uid": collection_uid,
            "filename": old_filename
        }, {"$set": kwargs})
        
        return result.modified_count
    
    def count_files_in_collection(self, user_id: str, collection_name: str) -> int:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        query = {
            "user_id": user_id,
            "collection_uid": collection_uid,
        }
        return self.file_collection.count_documents(query)

    def delete_file(self, user_id: str, collection_name: str, filename: str) -> int:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        if file_data := self.file_collection.find_one(
            {
                "user_id": user_id,
                "collection_uid": collection_uid,
                "filename": filename,
            }
        ):
            self.fs.delete(file_data["file_id"])
            self.file_collection.delete_one({
                "user_id": user_id,
                "collection_uid": collection_uid,
                "filename": filename
            })
            return 1

        return 0

    def delete_many_files(self, user_id: str, collection_name: str) -> int:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        query = {
            "user_id": user_id,
            "collection_uid": collection_uid,
        }
        cursor = self.file_collection.find(query)
        for doc in cursor:
            self.fs.delete(doc["file_id"])
        
        result = self.file_collection.delete_many(query)
        return result.deleted_count

    def get_all_files(self, user_id: str, collection_name: str, fetch_bytes: bool = False) -> List[FileModel]:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        cursor = self.file_collection.find({
            "user_id": user_id,
            "collection_uid": collection_uid
        })
        
        files = []
        for doc in cursor:
            if fetch_bytes:
                try:
                    doc["file_bytes"] = self.fs.get(doc["file_id"]).read()
                except NoFile:
                    doc["file_bytes"] = b""
            else:
                doc["file_bytes"] = b""
                
            files.append(FileModel(**doc))
        
        return files


class MessageDBManager:
    def __init__(self, connection_string: str, database_name: str) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.message_collection: Collection = self.db["messages"]
        self.message_collection.create_index("user_id", unique=False)

    def add_conversation(self, user_id: str, metadata: Dict[str, Any]) -> str:
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(metadata=metadata)
        self.message_collection.update_one(
            {"user_id": user_id},
            {"$set": {f"conversations.{conversation_id}": conversation.model_dump()}},
            upsert=True
        )
        return conversation_id

    def add_message(self, user_id: str, conversation_id: str, human_message: str, bot_response: str) -> None:
        message_pair = MessagePair(human_message=human_message, bot_response=bot_response)
        if not self.message_collection.count_documents({"user_id": user_id, f"conversations.{conversation_id}": {"$exists": True}}, limit=1):
            raise ValueError(f"No conversation found with conversation_id: {conversation_id} for user_id: {user_id}")

        self.message_collection.update_one(
            {"user_id": user_id},
            {"$push": {f"conversations.{conversation_id}.messages": message_pair.model_dump()}}
        )

    def get_messages(self, user_id: str, conversation_id: str) -> Optional[List[MessagePair]]:
        if user_data := self.message_collection.find_one(
            {"user_id": user_id}, {"conversations": {conversation_id: 1}}
        ):
            messages = user_data.get("conversations", {}).get(conversation_id, {}).get("messages", [])
            return [MessagePair(**message) for message in messages]
        else:
            return None
        
    def get_all_conversations(self, user_id: str) -> Optional[List[LatestConversation]]:
        if not (
            user_data := self.message_collection.find_one(
                {"user_id": user_id}, {"conversations": 1}
            )
        ):
            return None
        latest_conversations = []
        for conv_id, conv_data in user_data.get("conversations", {}).items():
            latest_message = MessagePair(**conv_data["messages"][-1]) if conv_data["messages"] else None
            latest_conversation = LatestConversation(conversation_id=conv_id, metadata=conv_data["metadata"], latest_message=latest_message)
            latest_conversations.append(latest_conversation)
        return latest_conversations

    def delete_conversation(self, user_id: str, conversation_id: str) -> int:
        result = self.message_collection.update_one(
            {"user_id": user_id},
            {"$unset": {f"conversations.{conversation_id}": 1}}
        )
        return result.modified_count

    def delete_all_conversations(self, user_id: str) -> int:
        result = self.message_collection.update_one(
            {"user_id": user_id},
            {"$set": {"conversations": {}}}
        )
        return result.modified_count
    
    def conversation_exists(self, user_id: str, conversation_id: str) -> bool:
        """
        Check if a conversation exists for a given user_id and conversation_id.

        Parameters:
            user_id (str): The user ID.
            conversation_id (str): The conversation ID.

        Returns:
            bool: True if the conversation exists, False otherwise.
        """
        exists = self.message_collection.find_one(
            {"user_id": user_id, f"conversations.{conversation_id}": {"$exists": True}},
            {"_id": 1}
        )
        return exists is not None



class TestFileDBManager(unittest.TestCase):
    
    def setUp(self) -> None:
        self.file_db_manager = FileDBManager()
        self.test_file  = FileModel(
            collection_name="test_collection",
            user_id="test_user",
            filename="test_file",
            friendly_filename="Test File",
            file_bytes=b"Test content",
            description="desc",
            filetype=".txt"
        )
        self.file_db_manager.add_file(self.test_file)
    
    def tearDown(self) -> None:
        self.file_db_manager.delete_file(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename)
    
    def test_add_file(self) -> None:
        new_file = FileModel(
            collection_name="new_collection",
            user_id="test_user",
            filename="test_file",
            friendly_filename="Test File",
            file_bytes=b"Test content",
            description="desc",
            filetype=".txt"
        )
        added_file = self.file_db_manager.add_file(new_file)
        self.assertEqual(added_file.filename, new_file.filename)
        self.file_db_manager.delete_file(new_file.user_id, new_file.collection_name, new_file.filename)
    
    def test_file_exists(self) -> None:
        self.assertTrue(self.file_db_manager.file_exists(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename))
        
    def test_get_file_by_name(self) -> None:
        file = self.file_db_manager.get_file_by_name(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename)
        self.assertIsNotNone(file)
        self.assertEqual(file.filename, self.test_file.filename)
    
    def test_get_all_files(self) -> None:
        files = self.file_db_manager.get_all_files(self.test_file.user_id, self.test_file.collection_name)
        self.assertTrue(len(files) > 0)
        
    def test_update_file(self) -> None:
        self.file_db_manager.update_file(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename, filename="updated_file")
        self.assertTrue(self.file_db_manager.file_exists(self.test_file.user_id, self.test_file.collection_name, "updated_file"))
        self.file_db_manager.update_file(self.test_file.user_id, self.test_file.collection_name, "updated_file", filename=self.test_file.filename)
    
    def test_delete_file(self) -> None:
        self.assertEqual(self.file_db_manager.delete_file(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename), 1)
        self.assertFalse(self.file_db_manager.file_exists(self.test_file.user_id, self.test_file.collection_name, self.test_file.filename))
    
class TestUserDBManager(unittest.TestCase):
    def setUp(self):
        self.db_manager = UserDBManager()
        self.test_user = UserModel(uid="test_uid", email="test_email")
        self.db_manager.add_user(self.test_user)

    def tearDown(self):
        self.db_manager.delete_user("test_uid")

    def test_add_user(self):
        user = UserModel(uid="1", email="user1@example.com")
        added_user = self.db_manager.add_user(user)
        self.assertEqual(added_user.uid, user.uid)
        self.db_manager.delete_user("1")

    def test_user_exists(self):
        self.assertTrue(self.db_manager.user_exists("test_uid"))

    def test_get_user_by_uid(self):
        user = self.db_manager.get_user_by_uid("test_uid")
        self.assertIsNotNone(user)
        self.assertEqual(user.uid, "test_uid")

    def test_get_all(self):
        users = self.db_manager.get_all()
        self.assertTrue(len(users) > 0)

    def test_insert_many(self):
        users = [UserModel(uid=str(i), email=f"user{i}@example.com") for i in range(2, 5)]
        self.db_manager.insert_many(users)
        for user in users:
            self.assertTrue(self.db_manager.user_exists(user.uid))
            self.db_manager.delete_user(user.uid)

    def test_update_user(self):
        self.db_manager.update_user("test_uid", email="new_email")
        user = self.db_manager.get_user_by_uid("test_uid")
        self.assertEqual(user.email, "new_email")

    def test_delete_user(self):
        self.assertEqual(self.db_manager.delete_user("test_uid"), 1)
        self.assertFalse(self.db_manager.user_exists("test_uid"))

class TestCollectionDBManager(unittest.TestCase):
    def setUp(self):
        self.db_manager = CollectionDBManager()
        self.test_collection = CollectionModel(user_uid="test_user", name="test_collection", vectordb_collection_name="test_vector_db")
        self.db_manager.add_collection(self.test_collection)

    def tearDown(self):
        self.db_manager.delete_collection("test_user", "test_collection")

    def test_add_collection(self):
        collection = CollectionModel(user_uid="1", name="collection1", vectordb_collection_name="vector_db1")
        added_collection = self.db_manager.add_collection(collection)
        self.assertEqual(added_collection.name, collection.name)
        self.db_manager.delete_collection("1", "collection1")

    def test_collection_exists(self):
        self.assertTrue(self.db_manager.collection_exists("test_collection", "test_user"))

    def test_get_collection_by_name_and_user(self):
        collection = self.db_manager.get_collection_by_name_and_user("test_collection", "test_user")
        self.assertIsNotNone(collection)
        self.assertEqual(collection.name, "test_collection")

    def test_get_all_by_user(self):
        collections = self.db_manager.get_all_by_user("test_user")
        self.assertTrue(len(collections) > 0)

    def test_update_collection(self):
        print(f"Updating collection: user_id=test_user, collection_id=test_collection, description=new_description")  # Debugging line
        self.db_manager.update_collection("test_user", "test_collection", description="new_description")
        collection = self.db_manager.get_collection_by_name_and_user("test_collection", "test_user")
        print(f"Retrieved collection description: {collection}")  # Debugging line
        self.assertEqual(collection.description, "new_description")

    def test_delete_collection(self):
        self.assertEqual(self.db_manager.delete_collection("test_user", "test_collection"), 1)
        self.assertFalse(self.db_manager.collection_exists("test_collection", "test_user"))



if __name__ == '__main__':
    unittest.main()