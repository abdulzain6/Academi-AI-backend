import base64
import tiktoken
import random
import img2pdf
from langchain.text_splitter import TokenTextSplitter
import Levenshtein, logging
from typing import List, Optional
from deepgram import DeepgramClient, PrerecordedOptions, BufferSource


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

        transcript_text = response["results"]["channels"][0]["alternatives"][0][
            "transcript"
        ]
        logging.info("Transcription completed successfully.")
        return transcript_text
    except Exception as e:
        logging.error(f"Error during transcription: {str(e)}")
        raise RuntimeError(f"Failed to transcribe audio: {str(e)}")
    

def find_most_similar(strings: List[str], target: str, max_distance: int = 5) -> Optional[str]:
    """
    Finds the most similar string in the list to the target string, with a constraint on the maximum Levenshtein distance.

    Args:
    strings (List[str]): List of strings to search through.
    target (str): The target string to compare with.
    max_distance (int): The maximum allowed Levenshtein distance.

    Returns:
    Optional[str]: The most similar string within the max_distance, or None if no such string exists.
    """
    closest_match = None
    min_distance = float('inf')

    for string in strings:
        distance = Levenshtein.distance(string, target)
        if distance < min_distance and distance <= max_distance:
            closest_match = string
            min_distance = distance

    return closest_match

def image_to_pdf_in_memory(image_path: str) -> bytes:
    """
    Convert an image to a PDF and return it as an in-memory bytes object using img2pdf.

    Args:
    image_path (str): The path to the input image file.

    Returns:
    bytes: The PDF file as a bytes object.
    """
    with open(image_path, "rb") as img_file:
        pdf_bytes = img2pdf.convert(img_file)

    return pdf_bytes

def file_to_base64(file_path: str) -> str:
    """Convert a file to a base64 string."""
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode()


def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def select_random_chunks(text: str, chunk_size: int, total_length: int) -> str:
    if num_tokens_from_string(text) < total_length:
        return text
    
    texts = TokenTextSplitter(chunk_size=chunk_size).split_text(text)
    random.shuffle(texts)
    selected_text = ''
    for chunk in texts:
        if num_tokens_from_string(selected_text) + num_tokens_from_string(chunk) <= total_length:
            selected_text += chunk
        else:
            break
            
    return selected_text