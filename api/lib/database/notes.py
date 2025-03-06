import io
import os
import tempfile
import pypandoc

from typing import Optional, List, Tuple
from bson import ObjectId
from docx import Document
from pydantic import BaseModel
from datetime import datetime
from pymongo import MongoClient, ASCENDING, TEXT
from api.lib.notes_maker.markdown_maker import MarkdownData, RGBColor, NoteCategory
from enum import Enum


class NoteType(Enum):
    LINK = "LINK"
    FILE = "FILE"
    TOPIC = "TOPIC"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"


class Note(BaseModel):
    instructions: str
    template_name: str
    notes_md: Optional[str] = None
    note_type: NoteType
    tilte: str
    is_public: bool = False
    category: NoteCategory = NoteCategory.OTHER


class NotesDatabase:
    def __init__(self, mongo_url: str, db_name: str):
        client = MongoClient(mongo_url)
        self.db = client[db_name]
        self.collection = self.db["notes"]

        # Create text index for notes_md field
        self.collection.create_index([("notes_md", TEXT)])

        # Create standard index for user_id
        self.collection.create_index([("user_id", ASCENDING)])

    def store_note(self, user_id: str, note: Note) -> str:
        note_data = {
            "user_id": user_id,
            "instructions": note.instructions,
            "template_name": note.template_name,
            "notes_md": note.notes_md,
            "created_at": datetime.utcnow(),
            "note_type": note.note_type.value,
            "title": note.tilte,
            "is_public": note.is_public,
            "category": note.category.value,
        }
        result = self.collection.insert_one(note_data)
        return str(result.inserted_id)


    def search_notes(self, query: str, limit: int = 10) -> List[Note]:
        """
        Search for notes based on text content in notes_md field.
        Only returns public notes.

        Args:
            user_id: The user ID to search notes for
            query: The text to search for in notes_md
            limit: Maximum number of results to return (default 10)

        Returns:
        List of matching Note objects
        """
        # Perform text search with user_id filter and public notes only
        results = (
            self.collection.find(
                {
                    "$and": [
                        {"is_public": True},
                        {"$text": {"$search": query}},
                    ]
                }
            )
            .sort([("created_at", -1)])  # Sort by creation date, newest first
            .limit(limit)
        )

        # Convert results to list of Note objects
        notes_list = []
        for note_data in results:
            note = Note(
                instructions=note_data["instructions"],
                template_name=note_data["template_name"],
                notes_md=note_data["notes_md"],
                note_type=NoteType(note_data["note_type"]),
                tilte=note_data["title"],
                is_public=True,  # These are definitely public
                category=NoteCategory(note_data.get("category", NoteCategory.OTHER.value)),
            )
            notes_list.append(note)
        return notes_list

    def get_notes_by_ids(self, note_ids: List[str]) -> List[Note]:
        """
        Get multiple notes by their IDs.
        If an ID doesn't exist, it's ignored in the results.

        Args:
            user_id: The user ID
            note_ids: List of note ID strings to retrieve

        Returns:
            List of Note objects
        """
        # Convert string IDs to ObjectId
        object_ids = []
        for id_str in note_ids:
            try:
                object_ids.append(ObjectId(id_str))
            except:
                # Skip invalid IDs
                continue

        if not object_ids:
            return []

        # Query MongoDB for all valid IDs
        notes_data = self.collection.find({"_id": {"$in": object_ids}})

        # Convert to Note objects
        notes = []
        for note_data in notes_data:
            notes.append(
                Note(
                    instructions=note_data["instructions"],
                    template_name=note_data["template_name"],
                    notes_md=note_data["notes_md"],
                    note_type=NoteType(note_data["note_type"]),
                    tilte=note_data["title"],
                    is_public=note_data.get("is_public", False),
                    category=NoteCategory(
                        note_data.get("category", NoteCategory.OTHER.value)
                    ),
                )
            )

        return notes

    def get_public_notes(
        self, page: int = 1, page_size: int = 10
    ) -> Tuple[List[Note], int]:
        """
        Retrieve public notes with pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Number of notes per page

        Returns:
            A tuple containing:
            - List of Note objects for the requested page
            - Total count of public notes
        """
        # Calculate skip for pagination
        skip = (page - 1) * page_size if page > 0 else 0

        # Query for public notes
        query = {"is_public": True}

        # Get total count for pagination info
        total_count = self.collection.count_documents(query)

        # Get paginated results
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )

        # Convert to Note objects
        notes = []
        for note_data in cursor:
            notes.append(
                Note(
                    instructions=note_data["instructions"],
                    template_name=note_data["template_name"],
                    notes_md=note_data["notes_md"],
                    note_type=NoteType(note_data["note_type"]),
                    tilte=note_data["title"],
                    is_public=note_data.get("is_public", True),
                    category=NoteCategory(
                        note_data.get("category", NoteCategory.OTHER.value)
                    ),
                )
            )

        return notes, total_count

    def get_notes_by_user(self, user_id: str):
        notes = self.collection.find({"user_id": user_id})
        notes_list = []
        for note in notes:
            notes_list.append(
                {
                    "user_id": note["user_id"],
                    "instructions": note["instructions"],
                    "template_name": note["template_name"],
                    "notes_md": note["notes_md"],
                    "id": str(note["_id"]),
                    "created_at": note["created_at"],
                    "note_type": note["note_type"],
                    "title": note["title"],
                    "is_public": note.get("is_public", False),
                    "category": note.get("category", NoteCategory.OTHER.value),
                }
            )
        return notes_list

    def get_note_for_user(self, user_id: str, note_id: ObjectId):
        note_data = self.collection.find_one({"_id": note_id, "user_id": user_id})
        if note_data:
            return {
                "user_id": note_data["user_id"],
                "instructions": note_data["instructions"],
                "template_name": note_data["template_name"],
                "notes_md": note_data["notes_md"],
                "id": str(note_data["_id"]),
                "created_at": note_data["created_at"],
                "note_type": note_data["note_type"],
                "title": note_data["title"],
            }
        return None

    def get_note(self, note_id: ObjectId):
        note_data = self.collection.find_one({"_id": note_id})
        if note_data:
            return {
                "user_id": note_data["user_id"],
                "instructions": note_data["instructions"],
                "template_name": note_data["template_name"],
                "notes_md": note_data["notes_md"],
                "id": str(note_data["_id"]),
                "created_at": note_data["created_at"],
                "note_type": note_data["note_type"],
                "title": note_data["title"],
                "is_public": note_data.get("is_public", False),
                "category": note_data.get("category", NoteCategory.OTHER.value),
            }
        return None

    def delete_note(self, user_id: str, note_id: ObjectId) -> bool:
        result = self.collection.delete_one({"_id": note_id, "user_id": user_id})
        return result.deleted_count > 0

    def make_notes(self, data: MarkdownData) -> io.BytesIO:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            pypandoc.convert_text(
                data.content,
                "docx",
                format="md",
                outputfile=temp_file.name,
                sandbox=True,
            )
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

    def update_notes_md(
        self, user_id: str, note_id: ObjectId, new_notes_md: str
    ) -> bool:
        result = self.collection.update_one(
            {"_id": note_id, "user_id": user_id}, {"$set": {"notes_md": new_notes_md}}
        )
        return result.modified_count > 0
