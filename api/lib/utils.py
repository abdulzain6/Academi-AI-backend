from io import BytesIO
from urllib.parse import urlparse, parse_qs
from typing import Union
from pdf2image import convert_from_path


import tempfile
import logging
import subprocess
import os
import json
import random
import time
import pypandoc


def docx_to_pdf_thumbnail(docx_file: BytesIO) -> BytesIO:
    """
    Converts DOCX to PDF and generates the first page thumbnail.
    
    Args:
        docx_file (BytesIO): The DOCX file input as a BytesIO object.
        
    Returns:
        BytesIO: Thumbnail of the first page as a PNG image in BytesIO format.
    """
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_docx:
        temp_docx.write(docx_file.read())
        temp_docx_path = temp_docx.name

    try:
        # Convert DOCX to PDF using pypandoc
        temp_pdf_path = temp_docx_path.replace(".docx", ".pdf")
        pypandoc.convert_file(temp_docx_path, 'pdf', outputfile=temp_pdf_path)

        # Convert the first page of the PDF to an image (thumbnail)
        images = convert_from_path(temp_pdf_path, first_page=1, last_page=1)
        
        if images:
            # Convert the image to a BytesIO object
            image_bytes = BytesIO()
            images[0].save(image_bytes, format='PNG')
            image_bytes.seek(0)
            return image_bytes
        else:
            raise Exception("No image generated from the PDF.")
    
    finally:
        # Clean up temporary files
        if os.path.exists(temp_docx_path):
            os.remove(temp_docx_path)
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

def convert_first_slide_to_image(pptx_path: str) -> BytesIO:
    """
    Converts the first slide of a PPTX presentation to an image using LibreOffice for conversion to PDF
    and pdf2image for converting the PDF's first page to an image. Ensures unique temporary files for
    each conversion and cleans up afterwards, with robust error handling.
    """
    # Initialize temporary file paths
    temp_pdf_path = None
    
    try:
        
        subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', "/tmp", pptx_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        temp_pdf_path = f"/tmp/{os.path.basename(pptx_path).replace('pptx', 'pdf')}"
        
        print(f"Pdf written to {temp_pdf_path}")
        # Verify PDF was created before proceeding
        if not os.path.exists(temp_pdf_path):
            print("PDF conversion failed or the PDF file was not created.")
            return BytesIO()

        # Convert the first page of the PDF to an image
        print("Converting to images")
        images = convert_from_path(temp_pdf_path, first_page=1, last_page=1)
        
        if images:
            # Convert the image to a BytesIO object
            image_bytes = BytesIO()
            images[0].save(image_bytes, format='PNG')
            image_bytes.seek(0)
            return image_bytes
        else:
            logging.error("No slides found in the PDF.")
            return BytesIO()
    except Exception as e:
        import traceback
        print(f"Error during slide to image conversion: {traceback.format_exception(e)}")
        return BytesIO()
    finally:
        # Clean up temporary files
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
        if 'pptx_path' in locals() and os.path.exists(pptx_path):
            os.remove(pptx_path)

def flatten_dict_to_string(data_dict, parent_key=''):
    """
    Recursively flattens a dictionary (including nested dictionaries) into a string.

    :param data_dict: Dictionary to flatten. Can be a dict or a string that represents a dict.
    :param parent_key: String to prepend to keys for nested dictionaries.
    :return: Flattened string.
    """
    items = []

    # If data_dict is a string, try to parse it as a JSON
    if isinstance(data_dict, str):
        try:
            data_dict = data_dict.replace("'", "\"")
            data_dict = json.loads(data_dict)
        except json.JSONDecodeError:
            # If not a valid JSON string, return the original string
            return data_dict

    for key, value in data_dict.items():
        new_key = f"{parent_key}.{key}" if parent_key else key

        # If value is a dictionary or a list, recursively flatten
        if isinstance(value, dict):
            items.append(flatten_dict_to_string(value, new_key))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                items.append(flatten_dict_to_string(item, f"{new_key}[{idx}]"))
        else:
            items.append(f"{new_key}: {value}")

    return ', '.join(item for item in items if item.split(': ')[1])

def timed_random_choice(items, interval=300):
    """
    Selects a random item based on a fixed time interval.

    :param items: List of items to choose from.
    :param interval: Time interval in seconds for which the choice should remain the same.
    :return: Selected item.
    """
    current_time = time.time()
    # Seed the random generator with the current time divided by the interval
    random.seed(current_time // interval)
    return random.choice(items)

def extract_schema_fields(schema: str) -> str:
    def parse_properties(properties):
        fields = []
        for key, value in properties.items():
            description = value.get("description")
            if description:
                field = f"{key} : {description}"
                fields.append(field)
        return fields

    def recursive_parse(schema_part):
        text = []
        if schema_part.get("type") == "object":
            fields = parse_properties(schema_part.get("properties", {}))
            text.extend(fields)
            for value in schema_part.get("properties", {}).values():
                child_text = recursive_parse(value)
                text.extend(child_text)
        elif schema_part.get("type") == "array":
            items = schema_part.get("items", {})
            text.extend(recursive_parse(items))
        return text

    return ", ".join(recursive_parse(schema))

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