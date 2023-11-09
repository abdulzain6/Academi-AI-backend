import requests
import pytesseract
import json
from typing import Optional
from PIL import Image


class ImageOCR:
    def __init__(self, app_id: str, app_key: str) -> None:
        self.app_id = app_id
        self.app_key = app_key

    def extract_text_with_tesseract(self, image_input: str) -> Optional[str]:
        """
        Extract text from an image using Tesseract.

        Parameters:
            image_input (Union[str, Any]): The path to the image file or the image file object.

        Returns:
            Optional[str]: The extracted text, or None if an error occurs.
        """
        try:
            image = Image.open(image_input)
            return pytesseract.image_to_string(image)
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def extract_text_with_mathpix(self, image_input: str) -> Optional[str]:
        """
        Extract text from an image using Mathpix API.

        Parameters:
            image_input (Union[str, Any]): The path to the image file or the image file object.

        Returns:
            Optional[str]: The extracted text, or None if an error occurs.
        """
        try:
            with open(image_input, "rb") as f:
                image_bytes = f.read()

            r = requests.post(
                "https://api.mathpix.com/v3/text",
                files={"file": image_bytes},
                data={
                    "options_json": json.dumps(
                        {
                            "numbers_default_to_math": True,
                            "math_inline_delimiters": ["$$", "$$"],
                            "math_display_delimiters": ["$$", "$$"],
                            "rm_spaces": True,
                        }
                    )
                },
                headers={"app_id": self.app_id, "app_key": self.app_key},
            )
            return r.json().get("text", None)
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def ocr_image(self, image_input: str) -> Optional[str]:
        return self.extract_text_with_mathpix(image_input)
