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
import random
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



def get_random_proxy() -> Optional[str]:
    url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=25"
    headers = {"Authorization": f"Token {os.getenv('WEBSHARE_KEY')}"}

    response = requests.get(url, headers=headers)
    data = response.json()
    if data.get("results"):
        # Select a random proxy from the list
        proxy = random.choice(data["results"])        
        # Construct the proxy string in the required format
        proxy_string = f"http://{proxy['username']}:{proxy['password']}@{proxy['proxy_address']}:{proxy['port']}"
        print(proxy_string)
        return proxy_string
    
    return None

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

def download_audio(video_url: str) -> str:
    """Download the audio from a YouTube video using yt-dlp with concurrent fragment downloads."""
    try:
        logger.info(f"Downloading audio from: {video_url}")
        rand = uuid.uuid4()
        ydl_opts = {
            'proxy' : get_random_proxy(),
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


def main(args):
    """DigitalOcean Function handler to extract transcript or generate it."""
    try:
        url = args.get("url")
        lang = args.get("lang", "en")
        
        if lang not in ALLOWED_LANGUAGES:
            return {"body": f"Language '{lang}' not supported.", "statusCode": 400}
        
        try:
            video_id = _parse_video_id(url)
            assert video_id
        except Exception as e:
            return {"body": f"Video ID extraction failed", "statusCode": 400}

        # Try to extract YouTube transcript
        try:
            proxy = get_random_proxy()
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=(lang,), proxies={"http" : proxy, "https" : proxy})
            transcript_text = " ".join([entry['text'] for entry in transcript])
            return {"body": transcript_text}
        
        # Fallback to download and transcribe audio if no transcript found
        except (NoTranscriptFound, Exception) as e:
            traceback.print_exception(e)
            audio_file = download_audio(url)
            transcription = transcribe_audio_with_deepgram(audio_file, lang)
            
            # Clean up audio file after processing
            if os.path.exists(audio_file):
                os.remove(audio_file)

            return {"body": transcription}
    
    except Exception as e:
        return {"body": f"Error: {str(e)}", "statusCode": 500}
    
    
print(main(
    {
    "url": "https://www.youtube.com/watch?si=XrDuCEpJZCxR27WO&v=BxS4FHswy5s&feature=youtu.be"
}
))