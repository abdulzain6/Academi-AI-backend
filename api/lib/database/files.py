from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from gridfs import GridFS, NoFile
from pydantic import BaseModel

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
    

class FileDBManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_manager,
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