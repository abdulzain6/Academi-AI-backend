import requests
import pytesseract
import io
import Levenshtein
from PIL import Image


class MermaidClient:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url

    def get_diagram_image(self, diagram_code: str, image_type: str = "svg") -> bytes:
        headers = {"Content-Type": "text/plain"}
        response = requests.post(
            f"{self.server_url}/generate?type={image_type}",
            data=diagram_code,
            headers=headers,
        )
        response.raise_for_status()
        image_content = response.content

        # Check for errors in the image using OCR
        img = Image.open(io.BytesIO(image_content))
        ocr_result = pytesseract.image_to_string(img)
        if (
            Levenshtein.distance(ocr_result.lower(), "Syntax error in graph".lower())
            < len("Syntax error in graph".lower()) // 2
        ):  # Allowing for half the length as error
            raise ValueError(
                f"Syntax error or diagram not supported. Use a different tool if needed"
            )

        return image_content
