import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..lib.notes_maker import make_notes_maker, get_available_note_makers_with_schema
from .auth import verify_token
from api.globals import redis_cache_manager, CACHE_DOCUMENT_URL_TEMPLATE, knowledge_manager
from youtube_search import YoutubeSearch

router = APIRouter()

class YoutubeSearchRequest(BaseModel):
    query: str = Field(description="Search query for YouTube videos.")
    num_results: int = Field(10, description="Number of search results to return, capped at 10.")
    
class MakeNotesRequest(BaseModel):
    notes_data: str = Field(json_schema_extra={"description" : "The data used to make the notes from. It must follow the correct schema accoridng to the template"})
    template_name: str = Field(json_schema_extra={"description" : "The template to make notes using"})

class GetYoutubeVideoTranscriptRequest(BaseModel):
    video_link: str = Field(description="The link of the youtube video to get transcript of.")





@router.post("/get_vid",
    description="Gets the transcript for a youtube video",
    openapi_extra={"x-openai-isConsequential": False}
)
def get_vid(
    get_vid_request: GetYoutubeVideoTranscriptRequest,
    _=Depends(verify_token),
):     
    try:
        contents, _, _ = knowledge_manager.load_web_youtube_link(metadata={}, youtube_link=get_vid_request.video_link)
        return {"transcript" : contents}
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@router.post("/search_youtube",
    description="Searches YouTube videos based on a query",
    openapi_extra={"x-openai-isConsequential": False}
)
def search_youtube(
    search_request: YoutubeSearchRequest,
    _=Depends(verify_token),
):
    try:
        results = YoutubeSearch(search_request.query, max_results=min(search_request.num_results, 10)).to_json()
        return {"search_results": results}
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@router.get("/templates", description="""
Used to get available templates for making notes along with the schema used to fill them
""", openapi_extra={"x-openai-isConsequential": False})
def get_available_templates(
    _ = Depends(verify_token),
):
    logging.info(f"Got get notes templates request GPTs")
    templates = get_available_note_makers_with_schema()
    logging.info(f"processed get notes templates request, GPTs")
    return {"note_templates": templates}

@router.post("/make_notes", 
description="Used to Make notes. It takes in a template name and the json dict containing user data according to the template that follows proper schema.",
openapi_extra={"x-openai-isConsequential": False})
def make_notes(notes_input: MakeNotesRequest, _ = Depends(verify_token)):
    try:
        notes_data = json.loads(notes_input.notes_data)
    except Exception:
        raise HTTPException(400, detail="Invalid json provided unable to load it")
    
    notes_maker = make_notes_maker(maker_type=notes_input.template_name, llm=None)
    notes_io = notes_maker.make_notes_from_dict(notes_data)
    doc_id = str(uuid.uuid4()) + ".docx"
    notes_bytes = notes_io.read()
    redis_cache_manager.set(key=doc_id, value=notes_bytes, ttl=18000, suppress=False)
    document_url = CACHE_DOCUMENT_URL_TEMPLATE.format(doc_id=doc_id)
    return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"