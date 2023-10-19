from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
class UserPoints(BaseModel):
    uid: str
    points: int
    last_claimed: Optional[datetime] = None  # Last time the daily bonus was claimed
    streak_count: int = 0
class UserModel(BaseModel):
    uid: str
    email: str
    display_name: Optional[str] = None
    photo_url: Optional[str] = None
    referred_by: Optional[str] = None


class CollectionModel(BaseModel):
    user_uid: str
    name: str
    description: Optional[str] = None
    vectordb_collection_name: str
    number_of_files: Optional[int] = 0
    collection_uid: str

class FileModel(BaseModel):
    collection_name: str
    user_id: str
    filename: str
    friendly_filename: str
    description: Optional[str] = None
    filetype: Optional[str] = None
    vector_ids: List[str] = []
    file_content: Optional[str] = None
    file_bytes: Optional[bytes] = b""
    
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