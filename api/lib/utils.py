from urllib.parse import urlparse, parse_qs
from typing import Union
import os

def contains_emoji(text: str) -> bool:
    return any(
        (
            0x1F600 <= ord(char) <= 0x1F64F  # Emoticons
            or 0x1F300 <= ord(char) <= 0x1F5FF  # Symbols & Pictographs
            or 0x1F680 <= ord(char) <= 0x1F6FF  # Transport & Map Symbols
            or 0x1F700 <= ord(char) <= 0x1F77F  # Alchemical Symbols
            or 0x2600 <= ord(char) <= 0x26FF  # Miscellaneous Symbols
            or 0x2700 <= ord(char) <= 0x27BF  # Dingbat Symbols
        )
        for char in text
    )

def get_file_extension(file_path: str):
    return os.path.splitext(file_path)[1]

def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

def format_url(url: str) -> Union[str, None]:
    if not url:
        return ""

    # Strip out 'http://' or 'https://' if they exist
    if url.startswith("http://"):
        url = url[len("http://"):]
    elif url.startswith("https://"):
        url = url[len("https://"):]

    return f"https://{url}"



def convert_youtube_url_to_standard(url: str) -> str:
    """
    Convert a YouTube URL to the standard format: https://www.youtube.com/watch?v=VIDEO_ID
    
    Parameters:
        url (str): The input YouTube URL.
        
    Returns:
        str: The converted YouTube URL in standard format.
    """
    if not url:
        return ""
    
    parsed_url = urlparse(url)
    
    if parsed_url.netloc == "youtu.be":
        video_id = parsed_url.path[1:]
    elif parsed_url.netloc in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed_url.path == "/watch":
            query_string = parse_qs(parsed_url.query)
            video_id = query_string.get("v")[0]
        elif parsed_url.path.startswith("/embed/"):
            video_id = parsed_url.path.split("/")[2]
        else:
            return url
    else:
        return url
    
    return f"https://www.youtube.com/watch?v={video_id}"