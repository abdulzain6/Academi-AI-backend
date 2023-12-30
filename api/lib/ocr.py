from abc import ABC, abstractmethod
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials
from typing import List
import time

class VisionOCR(ABC):
    @abstractmethod
    def perform_ocr(self, path: str) -> List[str]:
        pass


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