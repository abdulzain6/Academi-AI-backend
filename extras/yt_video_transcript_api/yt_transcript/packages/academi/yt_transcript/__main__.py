import time
from typing import Optional
from deepgram import DeepgramClient, PrerecordedOptions, BufferSource
from urllib.parse import parse_qs, urlparse
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

import requests
import os
import traceback
import tempfile
import uuid
import yt_dlp
import logging
import dotenv
import requests
from typing import Optional

dotenv.load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ALLOWED_LANGUAGES = [
    "bg", "ca", "zh", "zh-CN", "zh-Hans", "zh-TW", "zh-Hant", "zh-HK", 
    "cs", "da", "da-DK", "nl", "en", "en-US", "en-AU", "en-GB", "en-NZ", 
    "en-IN", "et", "fi", "nl-BE", "fr", "fr-CA", "de", "de-CH", "el", 
    "hi", "hu", "id", "it", "ja", "ko", "ko-KR", "lv", "lt", "ms", 
    "multi", "no", "pl", "pt", "pt-BR", "ro", "ru", "sk", "es", "es-419", 
    "sv", "sv-SE", "th", "th-TH", "tr", "uk", "vi"
]
ALLOWED_SCHEMAS = {"http", "https"}
ALLOWED_NETLOCK = {
    "youtu.be",
    "m.youtube.com",
    "youtube.com",
    "www.youtube.com",
    "www.youtube-nocookie.com",
    "vid.plus",
}


def _parse_video_id(url: str) -> Optional[str]:
    """Parse a youtube url and return the video id if valid, otherwise None."""
    parsed_url = urlparse(url)

    if parsed_url.scheme not in ALLOWED_SCHEMAS:
        return None

    if parsed_url.netloc not in ALLOWED_NETLOCK:
        return None

    path = parsed_url.path

    if path.endswith("/watch"):
        query = parsed_url.query
        parsed_query = parse_qs(query)
        if "v" in parsed_query:
            ids = parsed_query["v"]
            video_id = ids if isinstance(ids, str) else ids[0]
        else:
            return None
    else:
        path = parsed_url.path.lstrip("/")
        video_id = path.split("/")[-1]

    if len(video_id) != 11:  # Video IDs are 11 characters long
        return None

    return video_id

def download_audio(video_url: str, proxy: str) -> str:
    """Download the audio from a YouTube video using yt-dlp with concurrent fragment downloads."""
    try:
        logger.info(f"Downloading audio from: {video_url}")
        rand = uuid.uuid4()
        ydl_opts = {
            'proxy' : proxy,
            'format': 'bestaudio[ext=m4a]',  # Select the best audio format available (m4a in this case)
            'outtmpl': os.path.join(tempfile.gettempdir(), f'{rand}%(id)s.%(ext)s'),
            'concurrent_fragment_downloads': 8,
            'max_filesize': 200000000,  # Optional: Limit the maximum file size to 200 MB
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(video_url, download=True)
            audio_file = os.path.join(tempfile.gettempdir(), f"{rand}{result['id']}.m4a")
            logger.info(f"Audio downloaded successfully: {audio_file}")
            return audio_file
    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        raise RuntimeError(f"Failed to download audio: {str(e)}")

def transcribe_audio_with_deepgram(file_path: str, lang: str) -> str:
    """Transcribe the audio file using Deepgram API."""
    try:
        deepgram = DeepgramClient(DEEPGRAM_API_KEY)
        options = PrerecordedOptions(
            model="nova-2",
            language=lang,
            smart_format=True,
        )
        
        # Upload the audio file
        with open(file_path, 'rb') as audio_file:
            response = deepgram.listen.prerecorded.v("1").transcribe_file(BufferSource(buffer=audio_file.read()), options)
        
        transcript_text = response['results']['channels'][0]['alternatives'][0]['transcript']
        logger.info(f"Transcription completed successfully.")
        return transcript_text
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise RuntimeError(f"Failed to transcribe audio: {str(e)}")


def main(args: dict):
    """DigitalOcean Function handler to extract transcript or generate it."""
    
    url: str = args.get("url")
    lang: str = args.get("lang", "en")

    if not url:
        return {"body": "URL is required", "statusCode": 400}

    proxy: str = os.getenv("PROXY", "http://dprulefr-rotate:7obapq1qv8fl@p.webshare.io:80")
    print(f"Using proxy: {proxy}")
    
    for _ in range(5):
        try:
            video_id: str = _parse_video_id(url)
            if not video_id:
                return {"body": "Video ID extraction failed", "statusCode": 400}
            
            try:
                # Attempt to fetch the transcript in the requested language
                transcript = YouTubeTranscriptApi.get_transcript(
                    video_id, languages=(lang,), proxies={"http": proxy, "https": proxy}
                )
            except Exception:
                # Fetch the available transcripts when the requested language is not found
                available_transcripts = YouTubeTranscriptApi.list_transcripts(video_id, proxies={"http": proxy, "https": proxy})
                fallback_transcript = available_transcripts.find_transcript(
                    available_transcripts._manually_created_transcripts or 
                    available_transcripts._generated_transcripts
                )
                fallback_language = fallback_transcript.language_code
                
                # Retry fetching transcript with the fallback language
                transcript = YouTubeTranscriptApi.get_transcript(
                    video_id, languages=(fallback_language,), proxies={"http": proxy, "https": proxy}
                )
            
            # Combine the transcript text
            transcript_text = " ".join([entry['text'] for entry in transcript])
            return {"body": transcript_text, "statusCode": 200}
        
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)
    
    return {"body": "Error in getting transcript", "statusCode": 500}


print(main(
    {"url": "https://youtu.be/nbuyle1CsSM?feature=shared"}
))