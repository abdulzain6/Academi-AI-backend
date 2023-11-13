from langchain.text_splitter import TokenTextSplitter
import base64
import tiktoken
import random
import img2pdf

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
    texts = TokenTextSplitter(chunk_size=chunk_size).split_text(text)
    random.shuffle(texts)
    selected_text = ''
    for chunk in texts:
        if num_tokens_from_string(selected_text) + num_tokens_from_string(chunk) <= total_length:
            selected_text += chunk
        else:
            break
            
    return selected_text