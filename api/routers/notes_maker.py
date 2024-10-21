import asyncio
import logging
import tempfile

from fastapi.responses import StreamingResponse
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import require_points_for_feature, can_use_premium_model
from ..lib.notes_maker import make_notes_maker, get_available_note_makers
from ..globals import get_model, collection_manager, file_manager, knowledge_manager
from ..lib.ocr import ImageOCR
from .utils import select_random_chunks
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from deepgram import DeepgramClient, PrerecordedOptions, BufferSource
from concurrent.futures import ThreadPoolExecutor


router = APIRouter()
executor = ThreadPoolExecutor(max_workers=5)


class MakeNotesInput(BaseModel):
    data: Optional[str] = None
    url: Optional[str] = None
    collection_name: Optional[str] = None
    file_name: Optional[str] = None
    instructions: str
    template_name: str


def transcribe_audio_with_deepgram(audio_data: bytes) -> str:
    """Transcribe the audio data using Deepgram API."""
    try:
        deepgram = DeepgramClient()
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
        )
        
        response = deepgram.listen.prerecorded.v("1").transcribe_file(
            BufferSource(buffer=audio_data), options
        )
        
        transcript_text = response['results']['channels'][0]['alternatives'][0]['transcript']
        logging.info("Transcription completed successfully.")
        return transcript_text
    except Exception as e:
        logging.error(f"Error during transcription: {str(e)}")
        raise RuntimeError(f"Failed to transcribe audio: {str(e)}")


@router.post("/transcribe/")
async def transcribe(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
    play_integrity_verified = Depends(verify_play_integrity),
):
    """Endpoint to transcribe an uploaded audio file."""
    try:
        logging.info(f"Got transcription request from {user_id} (Notes maker)")
        audio_data = await file.read()

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(executor, transcribe_audio_with_deepgram, audio_data)
        
        return {"transcript": transcript}
    except Exception as e:
        logging.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ocr_image_to_string")
def ocr_image_route(
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    play_integrity_verified = Depends(verify_play_integrity),
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


@router.get("/templates")
def get_available_templates(
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    logging.info(f"Got get ppt templates request, {user_id}")
    templates = get_available_note_makers()
    logging.info(f"processed get ppt templates request, {user_id}")
    return {"note_templates": templates}


@router.post("/make_notes")
@require_points_for_feature("NOTES")
def make_notes(
    notes_input: MakeNotesInput,
    user_id: str = Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if not notes_input.data and not notes_input.collection_name and not notes_input.url:
        raise HTTPException(400, detail="Data, collection name or url must be provided")

    if notes_input.collection_name and not collection_manager.collection_exists(
        notes_input.collection_name, user_id
    ):
        raise HTTPException(400, detail="Collection not found!")

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
            data, _, _ = knowledge_manager.load_web_youtube_link({}, None, web_url=notes_input.url, injest=False)
        except ValueError as e:
            raise HTTPException(400, detail=f"Error: {e}")
        except Exception as e:
            logging.error(f"Error: {e}")
            raise HTTPException(400, detail=f"There was an issue in getting data from the url, Please try another url")


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
    if notes_input.template_name == "Text Notes":
        json_mode = False
    else:
        json_mode = True

    model = get_model({"temperature": 0.2}, False, premium_model, alt=True, json_mode=json_mode)

    try:
        notes_maker = make_notes_maker(notes_input.template_name, llm=model)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    
        

    content = select_random_chunks(data, 1350, 2700)
    data = notes_maker.make_notes_from_string(content, notes_input.instructions)
    data.seek(0)

    response = StreamingResponse(data, media_type="application/octet-stream")
    response.headers[
        "Content-Disposition"
    ] = f"attachment; filename={notes_input.template_name}.docx"
    return response
