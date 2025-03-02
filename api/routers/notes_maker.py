import asyncio
import base64
import logging
import tempfile

from bson import ObjectId
from api.config import SEARCHX_HOST
from api.lib.notes_maker.markdown_maker import MarkdownData
from api.lib.notes_maker.note_validation import add_note, is_note_worthy, search_notes
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import require_points_for_feature, can_use_premium_model
from ..lib.notes_maker.markdown_maker import MarkdownNotesMaker
from ..globals import (
    get_model,
    collection_manager,
    file_manager,
    knowledge_manager,
    notes_db,
)
from ..lib.ocr import ImageOCR
from ..lib.database.notes import Note as StoreNotesInput, NoteType
from .utils import transcribe_audio_with_deepgram
from .utils import select_random_chunks
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor


router = APIRouter()
executor = ThreadPoolExecutor(max_workers=5)


class MakeNotesInput(BaseModel):
    data: Optional[str] = None
    url: Optional[str] = None
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    instructions: Optional[str] = (
        "Create comprehensive and well-structured notes that summarize the main points, include relevant details, use clear headings and subheadings, incorporate bullet points or numbered lists for clarity, highlight key concepts or terms, and provide brief examples or explanations where necessary. Ensure the notes are concise yet informative, easy to read, and follow a logical flow."
    )
    note_type: NoteType
    is_public: bool = True


class MakeNotesInputWithTemplate(MakeNotesInput):
    template_name: str


class NoteResponse(BaseModel):
    note_id: str
    user_id: str
    instructions: str
    template_name: str
    thumbnail: str


class UpdateNoteInput(BaseModel):
    new_notes_md: str


class CreateNoteManually(MakeNotesInput):
    title: str
    data: str





@router.post("/transcribe/")
async def transcribe(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    """Endpoint to transcribe an uploaded audio file."""
    try:
        logging.info(f"Got transcription request from {user_id} (Notes maker)")
        audio_data = await file.read()

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            executor, transcribe_audio_with_deepgram, audio_data
        )

        return {"transcript": transcript}
    except Exception as e:
        logging.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr_image_to_string")
def ocr_image_route(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    play_integrity_verified=Depends(verify_play_integrity),
) -> Optional[str]:
    logging.info(f"Got ocr request, {user_id}")
    try:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write(file.file.read())
            temp_file_path = temp_file.name
            ocr_result = ImageOCR().perform_ocr(temp_file_path)
        logging.info(f"Successfully ocred {user_id}")
        return ocr_result.replace("\n", " ")

    except Exception as e:
        logging.error(f"Error in ocr {e}")
        raise HTTPException(400, f"Error: {e}") from e


@router.post("/make-notes-v2")
@require_points_for_feature("NOTES")
def make_notes(
    notes_input: MakeNotesInput,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if not notes_input.data and not notes_input.collection_name and not notes_input.url:
        raise HTTPException(400, detail="Data, Subject name or url must be provided")

    if notes_input.collection_name and not collection_manager.collection_exists(
        notes_input.collection_name, user_id
    ):
        raise HTTPException(400, detail="Subject not found!")

    if notes_input.file_name and not file_manager.file_exists(
        collection_uid=collection_manager.resolve_collection_uid(
            notes_input.collection_name, user_id=user_id
        ),
        user_id=user_id,
        filename=notes_input.file_name,
    ):
        raise HTTPException(400, detail="File not found!")

    if notes_input.data:
        data = notes_input.data
    elif notes_input.url:
        try:
            data, _, _ = knowledge_manager.load_web_youtube_link(
                {}, None, web_url=notes_input.url, injest=False
            )
        except ValueError as e:
            raise HTTPException(400, detail=f"Error: {e}")
        except Exception as e:
            logging.error(f"Error: {e}")
            raise HTTPException(
                400,
                detail=f"There was an issue in getting data from the url, Please try another url",
            )

    elif notes_input.file_name:
        file = file_manager.get_file_by_name(
            user_id=user_id,
            collection_name=notes_input.collection_name,
            filename=notes_input.file_name,
        )
        data = file.file_content
    else:
        files = file_manager.get_all_files(
            user_id=user_id, collection_name=notes_input.collection_name
        )
        data = "\n".join([file.file_content for file in files])

    model_name, premium_model = can_use_premium_model(user_id=user_id)
    model = get_model(
        {"temperature": 0.2}, False, premium_model, alt=False, json_mode=True
    )
    notes_maker = MarkdownNotesMaker(model, searxng_host=SEARCHX_HOST)

    content = select_random_chunks(data, 2000, 4500)

    title = notes_maker.generate_title(content)
    data = notes_maker.make_notes_from_string_return_string_only(
        content, notes_input.instructions, title=title
    )

    similar_to_other_notes = not is_note_worthy(data)
    notes_id = notes_db.store_note(
        user_id=user_id,
        note=StoreNotesInput(
            instructions=notes_input.instructions,
            template_name="Text Notes",
            notes_md=data,
            note_type=notes_input.note_type,
            tilte=title,
            is_public=not similar_to_other_notes and notes_input.is_public,
        ),
    )
    if not similar_to_other_notes and notes_input.is_public:
        logging.info("Adding note to knowledge manager")
        add_note(data, notes_id)
    return {"note_id": notes_id, "notes_markdown": data}


@router.post("/")
def create_note_manually(
    notes_input: CreateNoteManually,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    notes_id = notes_db.store_note(
        user_id=user_id,
        note=StoreNotesInput(
            instructions=notes_input.instructions,
            template_name="Text Notes",
            notes_md=notes_input.data,
            note_type=notes_input.note_type,
            tilte=notes_input.title,
        ),
    )
    return {"id": notes_id}


@router.get("/")
def get_all_notes(
    user_id=Depends(get_user_id), play_integrity_verified=Depends(verify_play_integrity)
):
    """Endpoint to get all notes for the current user."""
    notes = notes_db.get_notes_by_user(user_id)
    return notes


@router.get("/public")
def get_public_notes_endpoint(
    page: int = 1,
    page_size: int = 10,
    _=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
) -> list[StoreNotesInput]:
    return notes_db.get_public_notes(page, page_size)[0]


@router.get("/search")
def search_notes_repository(
    query: str,
    limit: int = 20,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
) -> list[StoreNotesInput]:
    limit = min(limit, 20)
    return reversed(search_notes(query, limit))


@router.get("/{note_id}")
def get_note_by_id(
    note_id: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    """Endpoint to get a specific note by note ID."""
    try:
        note_object_id = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note ID.")

    note = notes_db.get_note(note_object_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")

    if not note["is_public"] and note["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Note is not public")
    
    # Generate the file
    bytes_io = notes_db.make_notes(MarkdownData(content=note.get("notes_md")))

    # Convert BytesIO to base64
    bytes_io.seek(0)
    file_content = bytes_io.getvalue()
    base64_file = base64.b64encode(file_content).decode("utf-8")

    # Prepare the response
    response = {"note": note, "file_base64": base64_file}
    return response


@router.delete("/{note_id}", status_code=204)
def delete_note(
    note_id: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    """Endpoint to delete a specific note by note ID."""
    try:
        note_object_id = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note ID.")

    # Attempt to delete the note
    if not notes_db.delete_note(user_id, note_object_id):
        raise HTTPException(
            status_code=404, detail="Note not found or not authorized to delete."
        )

    return {"detail": "Note deleted successfully"}


@router.put("/{note_id}", status_code=200)
def update_notes(
    note_id: str,
    update_data: UpdateNoteInput,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    """Endpoint to update a specific note by note ID."""
    try:
        note_object_id = ObjectId(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note ID.")

    # Attempt to update the note
    if not notes_db.update_notes_md(user_id, note_object_id, update_data.new_notes_md):
        raise HTTPException(
            status_code=404, detail="Note not found or not authorized to update."
        )

    return {"detail": "Note updated successfully"}
