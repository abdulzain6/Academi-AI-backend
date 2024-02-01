import logging
import requests
import pytesseract
import json
from replicate.client import Client
from typing import Optional
from PIL import Image
from ..ocr import VisionOCR
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage


class ImageOCR:
    def __init__(self, app_id: str, app_key: str, alt_ocr: VisionOCR) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.alt_ocr = alt_ocr

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
        
    def gemini_ocr(self, image_path: str) -> str:
        llm = ChatGoogleGenerativeAI(model="gemini-pro-vision")
        return llm.invoke(
            [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "YOu are an OCR, Read the text in the image as it is, if there are maths equations use latex for them. Do not miss anything. You will return the text only. I want pure math latex not markdown latex.",
                        },
                        {
                            "type": "image_url",
                            "image_url": image_path
                        },
                    ]
                )
            ]
        ).content

    def ocr_image(self, image_input: str) -> Optional[str]:
        return self.gemini_ocr(image_input)
        if self.has_equations(image_path=image_input):
            logging.info("Using mathpix ocr")
            return self.extract_text_with_mathpix(image_input)
        else:
            logging.info("Using alt ocr")
            return self.alt_ocr.perform_ocr(image_input)
    
    def has_equations(self, image_path: str) -> bool:
        try:
            output = Client(timeout=5).run(
            "yorickvp/llava-13b:e272157381e2a3bf12df3a8edd1f38d1dbd736bbb7437277c8b34175f8fce358",
            input={"image": open(image_path, "rb"),
                "prompt" : "Does this image have maths equation in it? reply 'yes' or 'no' nothing else",
                "temperature" : 0.2,
                "max_tokens" : 1}
            )
            text: str = list(output)[0]
            if "yes" in text.lower():
                return True
            else:
                return False
        except Exception as e:
            logging.error(f"Error in llava: {e}")
            return True