from typing import List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from .collections import CollectionDBManager
from .files import FileDBManager
from .cache_manager import CacheProtocol
import uuid

class MessagePair(BaseModel):
    human_message: str
    bot_response: str
    
class ChatType(Enum):
    COLLECTION = "COLLECTION"
    FILE = "FILE"
    OTHER = "OTHER"
    SOLVER = "SOLVER"
    DELETED = "DELETED"
    
class ConversationMetadata(BaseModel):
    collection_uid: Optional[str] = None
    file_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    chat_type: ChatType = ChatType.OTHER
    
class ConversationResponse(BaseModel):
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    chat_type: ChatType = ChatType.OTHER
    
class Conversation(BaseModel):
    metadata: ConversationMetadata
    messages: List[MessagePair] = Field(default_factory=list)

    def custom_model_dump(self):
        data = self.model_dump(by_alias=True)
        data['metadata']['chat_type'] = data['metadata']['chat_type'].value
        return data

    
    
class LatestConversation(BaseModel):
    metadata: ConversationResponse
    latest_message: Optional[MessagePair]
    conversation_id: str

class UserLatestConversations(BaseModel):
    user_id: str
    conversations: List[LatestConversation] = Field(default_factory=list)


class MessageDBManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_dbmanager: CollectionDBManager,
        file_dbmanager: FileDBManager,
        cache_manager: CacheProtocol
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.message_collection: Collection = self.db["messages"]
        self.message_collection.create_index("user_id", unique=False)
        self.collection_dbmanager = collection_dbmanager
        self.file_dbmanager = file_dbmanager
        self.cache_manager = cache_manager
        
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
        self.cache_manager.delete(f"messages:{user_id}:{conversation_id}")
        return conversation_id

    def add_message(
        self, user_id: str, conversation_id: str, human_message: str, bot_response: str
    ) -> None:
        message_pair = MessagePair(
            human_message=human_message, bot_response=bot_response
        )
        # Before updating, check if the conversation exists
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
        # Invalidate cache
        self.cache_manager.delete(f"messages:{user_id}:{conversation_id}")


    def get_messages(
        self, user_id: str, conversation_id: str
    ) -> Optional[List[MessagePair]]:
        cached_data = self.cache_manager.get(f"messages:{user_id}:{conversation_id}")
        
        if cached_data is not None:
            return [MessagePair(**message) for message in cached_data]

        if user_data := self.message_collection.find_one(
            {"user_id": user_id}, {"conversations": {conversation_id: 1}}
        ):
            messages = (
                user_data.get("conversations", {})
                .get(conversation_id, {})
                .get("messages", [])
            )
            self.cache_manager.set(f"messages:{user_id}:{conversation_id}", messages)
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
            if not collection_name and metadata.chat_type in {
                ChatType.FILE,
                ChatType.COLLECTION,
            }:
                collection_name = "[<DELETED>]"
                metadata.chat_type = ChatType.DELETED

            if (
                self.file_dbmanager.file_exists(
                    user_id, metadata.collection_uid, metadata.file_name
                )
                or metadata.chat_type != ChatType.FILE
            ):
                file_name = metadata.file_name
            else:
                file_name = "[<DELETED>]"
                metadata.chat_type = ChatType.DELETED

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
        self.cache_manager.delete(f"messages:{user_id}:{conversation_id}")
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
