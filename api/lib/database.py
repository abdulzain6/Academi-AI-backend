from collections import deque
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional
from pymongo import MongoClient
import pymongo
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError
from gridfs import GridFS, NoFile
from .models import (
    ChatType,
    ConversationResponse,
    UserModel,
    CollectionModel,
    FileModel,
    Conversation,
    LatestConversation,
    MessagePair,
    ConversationMetadata,
    UserPoints,
)

import uuid


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
            collection_vector_ids = self.collection_manager.get_all_vector_ids(
                user_id, collection_name
            )
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
            self.user_collection.insert_many(
                [user_model.model_dump() for user_model in rows], ordered=False
            )
        except BulkWriteError as bwe:
            print(bwe.details)

    def update_user(self, uid: str, **kwargs: dict) -> int:
        if "uid" in kwargs:
            raise ValueError("Changing 'uid' is not allowed.")

        result = self.user_collection.update_one({"uid": uid}, {"$set": kwargs})
        return result.modified_count

    def delete_user(self, uid: str) -> int:
        if not self.user_exists(uid):
            return 0
        self.collection_manager.delete_all(uid)
        self.user_collection.delete_one({"uid": uid})
        return 1


class UserPointsManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        default_points: int = 10,
        daily_points: int = 3,
        weekly_daily_bonus_points: int = 10,
        max_ads_per_hour: int = 5,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.points_collection: Collection = self.db["user_points"]
        self.default_points = default_points
        self.daily_points = daily_points
        self.max_ads_per_hour = max_ads_per_hour
        self.weekly_daily_bonus_points = weekly_daily_bonus_points
        self.points_collection.create_index("uid", unique=True)
        self.ad_watch_timestamps = {}

    def can_increment_from_ad(self, uid: str) -> bool:
        now = datetime.now(timezone.utc)
        if uid not in self.ad_watch_timestamps:
            self.ad_watch_timestamps[uid] = deque([], maxlen=self.max_ads_per_hour)

        timestamps = self.ad_watch_timestamps[uid]

        # Remove timestamps older than 1 hour
        one_hour_ago = now - timedelta(hours=1)
        while timestamps and timestamps[0] < one_hour_ago:
            timestamps.popleft()

        if len(timestamps) < self.max_ads_per_hour:
            timestamps.append(now)
            return True

        return False

    def get_user_points(self, uid: str) -> UserPoints:
        if not self.user_exists(uid):
            logging.info(f"Creating points for user, {uid}")
            self.points_collection.insert_one(
                UserPoints(uid=uid, points=self.default_points).model_dump()
            )

        logging.info(f"Getting points for user, {uid}")
        data = self.points_collection.find_one({"uid": uid}, {"_id": 0})
        return UserPoints(**data)

    def user_exists(self, uid: str) -> bool:
        return self.points_collection.count_documents({"uid": uid}, limit=1) > 0

    def get_streak_day(self, uid: str) -> int:
        """
        Get the streak day for the user identified by uid.

        Returns:
            The streak day (integer).
        """
        user_points: UserPoints = self.get_user_points(uid)
        return user_points.streak_count

    def is_daily_bonus_claimed(self, uid: str) -> bool:
        """
        Check if the daily bonus has already been claimed by the user identified by uid.

        Returns:
            True if claimed, otherwise False.
        """
        user_points: UserPoints = self.get_user_points(uid)
        now = datetime.now(timezone.utc)
        last_claimed = user_points.last_claimed

        if last_claimed is None:
            return False

        # Ensure last_claimed is also offset-aware
        if (
            last_claimed.tzinfo is None
            or last_claimed.tzinfo.utcoffset(last_claimed) is None
        ):
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        return (now - last_claimed) < timedelta(days=1)

    def claim_daily_bonus(self, uid: str) -> int:
        try:
            logging.info(f"Getting points while claiming bonus for {uid}")
            user_points = self.get_user_points(uid)
        except pymongo.errors.PyMongoError as e:
            logging.error(f"Error getting points while claiming bonus for {uid}")
            raise ValueError("Database operation failed") from e

        now = datetime.now(timezone.utc)
        last_claimed: Optional[datetime] = user_points.last_claimed

        if last_claimed and last_claimed.tzinfo is None:
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        if last_claimed and now - last_claimed < timedelta(days=1):
            return 0

        streak_count: int = (
            user_points.streak_count
            if last_claimed and now - last_claimed < timedelta(days=2)
            else 0
        )
        streak_count += 1
        bonus_points = (
            10 if streak_count == self.weekly_daily_bonus_points else self.daily_points
        )

        try:
            logging.info(f"Incrementing points while claiming bonus for {uid}")
            self.increment_user_points(uid, bonus_points)
            self.points_collection.update_one(
                {"uid": uid},
                {"$set": {"last_claimed": now, "streak_count": streak_count % 7}},
            )
        except pymongo.errors.PyMongoError as exc:
            logging.error(f"Error incrementing points while claiming bonus for {uid}")
            raise ValueError("Database operation failed") from exc

        return bonus_points

    def increment_user_points(self, uid: str, points: int) -> int:
        if not self.user_exists(uid):
            self.points_collection.insert_one(
                UserPoints(uid=uid, points=self.default_points).model_dump()
            )
        result = self.points_collection.update_one(
            {"uid": uid}, {"$inc": {"points": points}}
        )
        return result.modified_count

    def decrement_user_points(self, uid: str, points: int) -> int:
        if not self.user_exists(uid):
            self.points_collection.insert_one(
                UserPoints(uid=uid, points=self.default_points).model_dump()
            )
        result = self.points_collection.update_one(
            {"uid": uid}, {"$inc": {"points": -points}}
        )
        return result.modified_count

    def time_until_daily_bonus(self, uid: str) -> timedelta:
        user_points: UserPoints = self.get_user_points(uid)
        now = datetime.now(timezone.utc)
        last_claimed: Optional[datetime] = user_points.last_claimed

        if last_claimed is None:
            return timedelta(seconds=0)

        if last_claimed.tzinfo is None:
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        time_since_last_claim = now - last_claimed

        if time_since_last_claim >= timedelta(days=1):
            return timedelta(seconds=0)

        return timedelta(days=1) - time_since_last_claim


class ReferralManager:
    def __init__(
        self,
        user_db_manager: UserDBManager,
        points_manager: UserPointsManager,
        referral_points: int = 15,
    ) -> None:
        self.user_db_manager = user_db_manager
        self.points_manager = points_manager
        self.referral_points = referral_points

    def apply_referral_code(self, uid: str, referral_code: str) -> None:
        user = self.user_db_manager.get_user_by_uid(uid)
        if not user:
            raise ValueError(f"User with ID {uid} does not exist.")

        if user.referred_by:
            raise ValueError("Referral code has already been applied for this user.")

        if referral_code == uid:
            raise ValueError("You cannot refer yourself.")

        if not self.user_db_manager.user_exists(referral_code):
            raise ValueError("Invalid referral code.")

        # Update the referred_by field for the user
        self.user_db_manager.update_user(uid, referred_by=referral_code)

        # Add points to the referrer
        self.points_manager.increment_user_points(referral_code, self.referral_points)

        self.points_manager.increment_user_points(uid, self.referral_points)


class CollectionDBManager:
    def __init__(self, connection_string: str, database_name: str) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]

        self.collection_collection: Collection = self.db["collections"]
        self.collection_collection.create_index("collection_uid", unique=True)
        self.collection_collection.create_index(
            [("name", 1), ("user_uid", 1)], unique=True
        )

        self.file_manager = FileDBManager(connection_string, database_name, self)

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


class FileDBManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_manager: CollectionDBManager,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.collection_manager = collection_manager
        self.file_collection: Collection = self.db["files"]
        self.fs = GridFS(self.db)

        # Create unique index
        self.file_collection.create_index(
            [("user_id", 1), ("collection_uid", 1), ("filename", 1)], unique=True
        )

    def resolve_collection_uid(self, user_id: str, collection_name: str) -> str:
        return self.collection_manager.resolve_collection_uid(collection_name, user_id)

    def add_file(self, file_model: FileModel) -> FileModel:
        collection_uid = self.resolve_collection_uid(
            file_model.user_id, file_model.collection_name
        )
        if self.file_exists(file_model.user_id, collection_uid, file_model.filename):
            raise ValueError("File already exists")

        file_id = self.fs.put(file_model.file_bytes, filename=file_model.filename)
        file_data = file_model.model_dump(exclude={"file_bytes"})
        file_data["file_id"] = file_id
        file_data["collection_uid"] = collection_uid  # Use collection_uid
        self.file_collection.insert_one(file_data)

        return file_model

    def get_file_by_name(
        self, user_id: str, collection_name: str, filename: str, bytes: bool = False
    ) -> Optional[FileModel]:
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
        return (
            self.file_collection.count_documents(
                {
                    "user_id": user_id,
                    "collection_uid": collection_uid,
                    "filename": filename,
                },
                limit=1,
            )
            > 0
        )

    def update_file(
        self,
        user_id: str,
        collection_name: str,
        old_filename: str,
        **kwargs: Dict[str, any],
    ) -> int:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        if "user_id" in kwargs or "collection_uid" in kwargs:
            raise ValueError("Changing 'user_id' or 'collection_uid' is not allowed.")

        new_filename = kwargs.get("filename", old_filename)
        if new_filename != old_filename and self.file_exists(
            user_id, collection_uid, new_filename
        ):
            raise ValueError(
                f"A file with the name {new_filename} already exists in the collection."
            )

        file_data = self.file_collection.find_one(
            {
                "user_id": user_id,
                "collection_uid": collection_uid,
                "filename": old_filename,
            }
        )
        if not file_data:
            return 0  # File not found

        if "file_bytes" in kwargs:
            self.fs.delete(file_data["file_id"])
            file_id = self.fs.put(kwargs["file_bytes"], filename=new_filename)
            kwargs["file_id"] = file_id
            del kwargs["file_bytes"]

        result = self.file_collection.update_one(
            {
                "user_id": user_id,
                "collection_uid": collection_uid,
                "filename": old_filename,
            },
            {"$set": kwargs},
        )

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
            self.file_collection.delete_one(
                {
                    "user_id": user_id,
                    "collection_uid": collection_uid,
                    "filename": filename,
                }
            )
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

    def get_all_files(
        self, user_id: str, collection_name: str, fetch_bytes: bool = False
    ) -> List[FileModel]:
        collection_uid = self.resolve_collection_uid(user_id, collection_name)
        cursor = self.file_collection.find(
            {"user_id": user_id, "collection_uid": collection_uid}
        )

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
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_dbmanager: CollectionDBManager = None,
        file_dbmanager: FileDBManager = None,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.message_collection: Collection = self.db["messages"]
        self.message_collection.create_index("user_id", unique=False)
        if not collection_dbmanager:
            self.collection_dbmanager = CollectionDBManager(
                connection_string, database_name
            )
        else:
            self.collection_dbmanager = collection_dbmanager

        if not file_dbmanager:
            self.file_dbmanager = FileDBManager(
                connection_string, database_name, collection_dbmanager
            )
        else:
            self.file_dbmanager = file_dbmanager

    def add_conversation(self, user_id: str, metadata: ConversationMetadata) -> str:
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(metadata=metadata)
        self.message_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"conversations.{conversation_id}": conversation.custom_model_dump()
                }
            },
            upsert=True,
        )
        return conversation_id

    def add_message(
        self, user_id: str, conversation_id: str, human_message: str, bot_response: str
    ) -> None:
        message_pair = MessagePair(
            human_message=human_message, bot_response=bot_response
        )
        if not self.message_collection.count_documents(
            {"user_id": user_id, f"conversations.{conversation_id}": {"$exists": True}},
            limit=1,
        ):
            raise ValueError(
                f"No conversation found with conversation_id: {conversation_id} for user_id: {user_id}"
            )

        self.message_collection.update_one(
            {"user_id": user_id},
            {
                "$push": {
                    f"conversations.{conversation_id}.messages": message_pair.model_dump()
                }
            },
        )

    def get_messages(
        self, user_id: str, conversation_id: str
    ) -> Optional[List[MessagePair]]:
        if user_data := self.message_collection.find_one(
            {"user_id": user_id}, {"conversations": {conversation_id: 1}}
        ):
            messages = (
                user_data.get("conversations", {})
                .get(conversation_id, {})
                .get("messages", [])
            )
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
            latest_message = (
                MessagePair(**conv_data["messages"][-1])
                if conv_data["messages"]
                else None
            )

            metadata = ConversationMetadata.model_validate(conv_data.get("metadata"))
            collection_name = self.collection_dbmanager.get_collection_name_by_uid(
                metadata.collection_uid
            )
            if not collection_name and metadata.chat_type in {ChatType.FILE, ChatType.COLLECTION}:
                collection_name = "[<DELETED>]"

            if self.file_dbmanager.file_exists(
                user_id, metadata.collection_uid, metadata.file_name
            ) or metadata.chat_type != ChatType.FILE:
                file_name = metadata.file_name
            else:
                file_name = "[<DELETED>]"

            latest_conversation = LatestConversation(
                conversation_id=conv_id,
                metadata=ConversationResponse(
                    collection_name=collection_name,
                    file_name=file_name,
                    timestamp=metadata.timestamp,
                    chat_type=metadata.chat_type,
                ),
                latest_message=latest_message,
            )
            latest_conversations.append(latest_conversation)
        return latest_conversations

    def delete_conversation(self, user_id: str, conversation_id: str) -> int:
        result = self.message_collection.update_one(
            {"user_id": user_id}, {"$unset": {f"conversations.{conversation_id}": 1}}
        )
        return result.modified_count

    def delete_all_conversations(self, user_id: str) -> int:
        result = self.message_collection.update_one(
            {"user_id": user_id}, {"$set": {"conversations": {}}}
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
            {"_id": 1},
        )
        return exists is not None
