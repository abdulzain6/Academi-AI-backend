import base64
import uuid
from io import BytesIO
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional, List


class Presentation(BaseModel):
    topic: str
    instructions: str
    number_of_pages: int


class MongoDBPresentationStore:
    def __init__(self, uri: str, db_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.fs = GridFS(self.db)
        self.collection = self.db["presentations"]

    def store_presentation(self, user_id: str, presentation: Presentation, pptx_file: BytesIO, thumbnail_file: BytesIO) -> ObjectId:
        """Stores the presentation with the user_id along with pptx and thumbnail files, with unique filenames."""
        
        # Generate a unique UUID for this presentation
        unique_id = str(uuid.uuid4())
        
        # Ensure filenames are unique by including user_id and a UUID
        pptx_id = self.fs.put(pptx_file, filename=f"{user_id}_{presentation.topic}_{unique_id}.pptx")
        thumbnail_id = self.fs.put(thumbnail_file, filename=f"{user_id}_{presentation.topic}_thumbnail_{unique_id}.png")
        
        # Store the presentation metadata along with the file IDs and user_id
        presentation_data = {
            "user_id": user_id,
            "topic": presentation.topic,
            "instructions": presentation.instructions,
            "number_of_pages": presentation.number_of_pages,
            "pptx_id": pptx_id,
            "thumbnail_id": thumbnail_id,
            "unique_id": unique_id  # Store UUID for reference if needed
        }
        return self.collection.insert_one(presentation_data).inserted_id

    def get_presentation(self, user_id: str, presentation_id: ObjectId) -> Optional[dict]:
        """Retrieves a specific presentation for the given user along with base64-encoded pptx and thumbnail files."""
        
        # Find the presentation by both user_id and presentation_id to ensure ownership
        presentation_data = self.collection.find_one({"_id": presentation_id, "user_id": user_id})
        
        if presentation_data:
            # Read and encode the PPTX and thumbnail files to base64
            pptx_file = self.fs.get(presentation_data["pptx_id"]).read()
            thumbnail_file = self.fs.get(presentation_data["thumbnail_id"]).read()
            
            # Convert binary files to base64 strings
            pptx_base64 = base64.b64encode(pptx_file).decode('utf-8')
            thumbnail_base64 = base64.b64encode(thumbnail_file).decode('utf-8')
            
            # Return the presentation data with base64-encoded files
            return {
                "user_id": presentation_data["user_id"],
                "topic": presentation_data["topic"],
                "instructions": presentation_data["instructions"],
                "number_of_pages": presentation_data["number_of_pages"],
                "pptx_file": pptx_base64,         # Base64-encoded pptx file
                "thumbnail_file": thumbnail_base64 # Base64-encoded thumbnail file
            }
        
        # Return None if no presentation is found or if the user_id doesn't match
        return None

    def get_presentations_by_user(self, user_id: str) -> List[dict]:
        """Retrieves all presentations for a given user_id."""
        presentations = self.collection.find({"user_id": user_id})
        result = []
        for presentation_data in presentations:
            thumbnail_file = self.fs.get(presentation_data["thumbnail_id"]).read()
            thumbnail_base64 = base64.b64encode(thumbnail_file).decode('utf-8')

            result.append({
                "user_id": presentation_data["user_id"],
                "topic": presentation_data["topic"],
                "instructions": presentation_data["instructions"],
                "number_of_pages": presentation_data["number_of_pages"],
                "thumbnail_file": thumbnail_base64,
                "id" : str(presentation_data["_id"])
            })
        return result

    def delete_presentation(self, user_id: str, presentation_id: ObjectId) -> bool:
        """Deletes a specific presentation and its associated files."""
        presentation_data = self.collection.find_one({"_id": presentation_id, "user_id": user_id})
        
        if presentation_data:
            # Remove the files from GridFS
            self.fs.delete(presentation_data["pptx_id"])
            self.fs.delete(presentation_data["thumbnail_id"])
            
            # Remove the presentation record from the collection
            self.collection.delete_one({"_id": presentation_id, "user_id": user_id})
            return True
        return False
