import uuid
from bson import ObjectId
from pydantic import BaseModel
from io import BytesIO
from pymongo import MongoClient
import gridfs, base64

class MakeNotesInput(BaseModel):
    instructions: str
    template_name: str


class NotesDatabase:
    def __init__(self, mongo_url: str, db_name: str):
        """Initialize the NotesDatabase with a MongoDB connection URL and database name."""
        client = MongoClient(mongo_url)
        self.db = client[db_name]
        self.collection = self.db["notes"]
        self.fs = gridfs.GridFS(self.db)
    
    def store_note(self, user_id: str, note: MakeNotesInput, file: BytesIO, thumbnail: BytesIO):
        """Store a note along with the file and thumbnail in GridFS."""
        file.seek(0)
        thumbnail.seek(0)
    
        file_id = self.fs.put(file, filename=f"{note.template_name}_{uuid.uuid4()}.docx")
        thumbnail_id = self.fs.put(thumbnail, filename=f"{note.template_name}__{uuid.uuid4()}thumbnail.png")

        note_data = {
            "user_id": user_id,
            "instructions": note.instructions,
            "template_name": note.template_name,
            "file_id": file_id,
            "thumbnail_id": thumbnail_id
        }
        self.collection.insert_one(note_data)

    def get_notes_by_user(self, user_id: str):
        """Retrieve all notes for a specific user, with base64-encoded thumbnails (no files)."""
        notes = self.collection.find({"user_id": user_id})
        notes_list = []
        for note in notes:
            thumbnail_file = self.fs.get(note["thumbnail_id"]).read()
            thumbnail_base64 = base64.b64encode(thumbnail_file).decode('utf-8')
            
            notes_list.append({
                "user_id": note["user_id"],
                "instructions": note["instructions"],
                "template_name": note["template_name"],
                "thumbnail_base64": thumbnail_base64,
                "id" : str(note["_id"])
            })
        return notes_list

    def get_note_with_file(self, user_id: str, note_id: ObjectId):
        """Retrieve a specific note with the file and thumbnail."""
        note_data = self.collection.find_one({"_id": note_id, "user_id": user_id})
        
        if note_data:
            file = self.fs.get(note_data["file_id"]).read()
            print(len(file))
            thumbnail_file = self.fs.get(note_data["thumbnail_id"]).read()
            file_base64 = base64.b64encode(file).decode('utf-8')
            thumbnail_base64 = base64.b64encode(thumbnail_file).decode('utf-8')


            return {
                "user_id": note_data["user_id"],
                "instructions": note_data["instructions"],
                "template_name": note_data["template_name"],
                "file_base64": file_base64,
                "thumbnail_base64": thumbnail_base64,
                "id" : str(note_data["_id"])
            }
        return None

    def delete_note(self, user_id: str, note_id: ObjectId) -> bool:
        """Delete a note by ID if it belongs to the user."""
        note = self.collection.find_one({"_id": note_id, "user_id": user_id})
        if not note:
            return False

        # Delete associated files from GridFS
        self.fs.delete(note["thumbnail_id"])
        self.fs.delete(note["file_id"])

        # Delete the note document
        self.collection.delete_one({"_id": note_id, "user_id": user_id})
        return True