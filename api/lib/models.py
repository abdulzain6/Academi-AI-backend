from typing import List, Optional
from pydantic import BaseModel


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

class FileModel(BaseModel):
    collection_name: str
    user_id: str
    filename: str
    friendly_filename: str
    description: str = None
    filetype: Optional[str] = None
    vector_ids: List[str] = []
    file_content: Optional[str] = None
    file_bytes: Optional[bytes] = b""