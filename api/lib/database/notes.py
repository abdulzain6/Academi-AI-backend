import io
import os
import tempfile
import pypandoc
from typing import Optional
from bson import ObjectId
from docx import Document
from pydantic import BaseModel
from datetime import datetime
from pymongo import MongoClient
from api.lib.notes_maker.markdown_maker import MarkdownData, RGBColor
from enum import Enum


class NoteType(Enum):
    LINK = "LINK"
    FILE = "FILE"
    TOPIC = "TOPIC"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"


class MakeNotesInput(BaseModel):
    instructions: str
    template_name: str
    notes_md: Optional[str] = None
    note_type: NoteType
    tilte: str


class NotesDatabase:
    def __init__(self, mongo_url: str, db_name: str):
        client = MongoClient(mongo_url)
        self.db = client[db_name]
        self.collection = self.db["notes"]

    def store_note(self, user_id: str, note: MakeNotesInput) -> str:
        note_data = {
            "user_id": user_id,
            "instructions": note.instructions,
            "template_name": note.template_name,
            "notes_md": note.notes_md,
            "created_at": datetime.utcnow(),
            "note_type" : note.note_type.value,
            "title" : note.tilte
        }
        result = self.collection.insert_one(note_data)
        return str(result.inserted_id)
    
    def get_notes_by_user(self, user_id: str):
        notes = self.collection.find({"user_id": user_id})
        notes_list = []
        for note in notes:
            notes_list.append({
                "user_id": note["user_id"],
                "instructions": note["instructions"],
                "template_name": note["template_name"],
                "notes_md": note["notes_md"],
                "id": str(note["_id"]),
                "created_at": note["created_at"],
                "note_type" : note["note_type"],
                "title" : note["title"]
            })
        return notes_list

    def get_note(self, user_id: str, note_id: ObjectId):
        note_data = self.collection.find_one({"_id": note_id, "user_id": user_id})
        
        if note_data:
            return {
                "user_id": note_data["user_id"],
                "instructions": note_data["instructions"],
                "template_name": note_data["template_name"],
                "notes_md": note_data["notes_md"],
                "id": str(note_data["_id"]),
                "created_at": note_data["created_at"],
                "note_type" : note_data["note_type"],
                "title" : note_data["title"]
            }
        return None

    def delete_note(self, user_id: str, note_id: ObjectId) -> bool:
        result = self.collection.delete_one({"_id": note_id, "user_id": user_id})
        return result.deleted_count > 0

    def make_notes(self, data: MarkdownData) -> io.BytesIO:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(data.content, 'docx', format='md', outputfile=temp_file.name, sandbox=True)
            temp_file_path = temp_file.name

        doc = Document(temp_file_path)

        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)

        file_obj = io.BytesIO()
        doc.save(file_obj)
        file_obj.seek(0)

        os.unlink(temp_file_path)
        return file_obj

    def update_notes_md(self, user_id: str, note_id: ObjectId, new_notes_md: str) -> bool:
        result = self.collection.update_one(
            {"_id": note_id, "user_id": user_id},
            {"$set": {"notes_md": new_notes_md}}
        )
        return result.modified_count > 0