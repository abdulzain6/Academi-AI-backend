from fastapi import APIRouter, Depends, HTTPException
from .auth import verify_token
from pydantic import BaseModel, Field
from api.globals import knowledge_manager

router = APIRouter()

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