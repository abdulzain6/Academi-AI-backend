from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

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

class Conversation(BaseModel):
    metadata: Dict[str, Any]
    messages: List[MessagePair] = Field(default_factory=list)

    
class LatestConversation(BaseModel):
    metadata: Dict[str, Any]
    latest_message: Optional[MessagePair]
    conversation_id: str

class UserLatestConversations(BaseModel):
    user_id: str
    conversations: List[LatestConversation] = Field(default_factory=list)

class ConversationMetadata(BaseModel):
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    extra_data: Optional[Dict[str, str]] = Field(None)
