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
    def gemini_ocr(self, image_path: str) -> str:
        llm = ChatGoogleGenerativeAI(model="gemini-pro-vision")
        return llm.invoke(
            [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "You are an OCR, Read the text in the image as it is, if there are maths equations use latex for them. Do not miss anything. You will return the text only. I want pure math latex not markdown latex.",
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