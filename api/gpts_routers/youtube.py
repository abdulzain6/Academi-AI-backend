import os
import uuid
import yt_dlp
from fastapi import APIRouter, Depends, HTTPException
from .auth import verify_token
from pydantic import BaseModel, Field
from api.globals import knowledge_manager, redis_cache_manager, CACHE_VIDEO_URL_TEMPLATE
from youtube_search import YoutubeSearch


router = APIRouter()

class GetYoutubeVideoTranscriptRequest(BaseModel):
    video_link: str = Field(description="The link of the youtube video to get transcript of.")
    
class YoutubeSearchRequest(BaseModel):
    query: str = Field(description="Search query for YouTube videos.")
    num_results: int = Field(10, description="Number of search results to return, capped at 10.")

class YoutubeDownloadRequest(BaseModel):
    video_url: str = Field(description="The URL of the YouTube video to download.")


@router.post("/get_vid",
    description="Gets the transcript for a youtube video",
    openapi_extra={"x-openai-isConsequential": False}
)
def get_vid(
    get_vid_request: GetYoutubeVideoTranscriptRequest,
    _=Depends(verify_token),
):     
    try:
        contents, _, _ = knowledge_manager.load_web_youtube_link(metadata={}, youtube_link=get_vid_request.video_link, injest=False)
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
    
    
@router.post("/download_youtube",
    description="Downloads a youtube video",
    openapi_extra={"x-openai-isConsequential": False})
def download_youtube(
    download_request: YoutubeDownloadRequest,
    _=Depends(verify_token),
):
    try:
        rand_id = str(uuid.uuid4()) + ".mp4"
        ydl_opts = {
            'concurrent_fragment_downloads': 8,
            'format': 'bestvideo[ext=mp4][height=720]+bestaudio[ext=m4a]/best[ext=mp4][height=720]',
            'outtmpl': f'/tmp/{rand_id}',
            'max_filesize': 200000000
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([download_request.video_url])
            video_path = f'/tmp/{rand_id}'
            with open(video_path, 'rb') as file:
                redis_cache_manager.set(key=rand_id, ttl=18000, value=file.read())
        
        try:
            os.remove(video_path)  # Delete the temporary file
        except Exception:
            pass
        
        return {"download_link": CACHE_VIDEO_URL_TEMPLATE.format(video_id=rand_id)}
    except Exception as e:
        raise HTTPException(400, detail=str(e))