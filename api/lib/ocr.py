from abc import ABC, abstractmethod
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials
from io import BytesIO
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
from langchain.schema import HumanMessage
from PIL import Image
import time
import base64

class VisionOCR(ABC):
    @abstractmethod
    def perform_ocr(self, path: str) -> str:
        pass


class ImageOCR(VisionOCR):        
    def gpt_ocr(self, image_path: str, model_name: str = "gemini-1.5-flash-8b") -> str:
        llm = ChatGoogleGenerativeAI(
            **{
                "model": model_name,
                "request_timeout": 60,
                "max_retries": 4,
                "safety_settings" : {
                    HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DEROGATORY: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_TOXICITY: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_VIOLENCE: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUAL: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_MEDICAL: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            }       
        )

        with Image.open(image_path) as img:
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        response = llm.invoke(
            [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text" :"You are an OCR. Return the text in the image as it is, if there are math equations use LaTeX for them. Do not miss anything. You will return the text only. I want pure math LaTeX, not markdown LaTeX. I need text back. Do not miss anything. If there are images, add a description of the images or text from them as is. Do not miss any text get everything!"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded_image}"                            }
                        }
                    ]
                )
            ]
        )
        return response.content

    def perform_ocr(self, image_input: str) -> Optional[str]:
        return self.gpt_ocr(image_input)


class AzureOCR(VisionOCR):
    def __init__(self, endpoint: str, subscription_key: str):
        self.client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))

    def perform_ocr(self, path: str) -> str:
        """Detects and extracts text from an image using Azure OCR."""
        with open(path, "rb") as image_stream:
            read_response = self.client.read_in_stream(image_stream, raw=True)

        # Extracting operation location from response header
        read_operation_location = read_response.headers["Operation-Location"]
        operation_id = read_operation_location.split("/")[-1]

        # Wait for the read operation to complete
        while True:
            read_result = self.client.get_read_result(operation_id)
            if read_result.status not in [OperationStatusCodes.not_started, OperationStatusCodes.running]:
                break
            time.sleep(1)

        # Extracting text from the result
        text = ""
        if read_result.status == OperationStatusCodes.succeeded:
            for text_result in read_result.analyze_result.read_results:
                for line in text_result.lines:
                    for word in line.words:
                        text += word.text + " "
                    text = text.strip() + "\n"  # Add a newline at the end of each line

        return text