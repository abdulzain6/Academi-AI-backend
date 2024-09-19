import os
import tempfile
import uuid
import yt_dlp
import logging
import dotenv
from deepgram import DeepgramClient, PrerecordedOptions, BufferSource
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from langchain_community.document_loaders import YoutubeLoader

dotenv.load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class YouTubeLink(BaseModel):
    url: str
    lang: str = "en"

def download_audio(video_url: str) -> str:
    """Download the audio from a YouTube video using yt-dlp with concurrent fragment downloads."""
    try:
        logger.info(f"Downloading audio from: {video_url}")
        rand = uuid.uuid4()
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tempfile.gettempdir(), f'{rand}%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'concurrent_fragment_downloads': 8,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(video_url, download=True)
            audio_file = os.path.join(tempfile.gettempdir(), f"{rand}{result['id']}.mp3")
            logger.info(f"Audio downloaded successfully: {audio_file}")
            return audio_file
    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to download audio: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"Failed to transcribe audio: {str(e)}")

@app.post("/extract-transcript/")
def extract_transcript(link: YouTubeLink):
    """Extract the transcript from a YouTube video or generate it if unavailable."""
    try:
        try:
            allowed_languages = [
                "bg", "ca", "zh", "zh-CN", "zh-Hans", "zh-TW", "zh-Hant", "zh-HK", 
                "cs", "da", "da-DK", "nl", "en", "en-US", "en-AU", "en-GB", "en-NZ", 
                "en-IN", "et", "fi", "nl-BE", "fr", "fr-CA", "de", "de-CH", "el", 
                "hi", "hu", "id", "it", "ja", "ko", "ko-KR", "lv", "lt", "ms", 
                "multi", "no", "pl", "pt", "pt-BR", "ro", "ru", "sk", "es", "es-419", 
                "sv", "sv-SE", "th", "th-TH", "tr", "uk", "vi"
            ]
            assert link.lang in allowed_languages
        except AssertionError:
            raise HTTPException(
                status_code=400, 
                detail="Languages must be one of the following: bg, ca, zh, zh-CN, zh-Hans, zh-TW, zh-Hant, zh-HK, cs, da, da-DK, nl, en, en-US, en-AU, en-GB, en-NZ, en-IN, et, fi, nl-BE, fr, fr-CA, de, de-CH, el, hi, hu, id, it, ja, ko, ko-KR, lv, lt, ms, multi, no, pl, pt, pt-BR, ro, ru, sk, es, es-419, sv, sv-SE, th, th-TH, tr, uk, vi"
            )

        video_id = YoutubeLoader.extract_video_id(link.url)
        logger.info(f"Extracting transcript for video ID: {video_id}")

        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=(link.lang,))
            transcript_text = " ".join([entry['text'] for entry in transcript])
            logger.info(f"Transcript found and extracted successfully.")
            return {"transcript": transcript_text}
        except (Exception, NoTranscriptFound) as e:
            logger.warning(f"No transcript found, downloading audio for transcription. {e}")
            audio_file = download_audio(link.url)
            transcription = transcribe_audio_with_deepgram(audio_file, link.lang)

            if os.path.exists(audio_file):
                os.remove(audio_file)
                logger.info(f"Audio file cleaned up after processing.")

            return {"transcript": transcription}

    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing video: {str(e)}")
