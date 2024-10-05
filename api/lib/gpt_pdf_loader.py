import base64, logging

from io import BytesIO
import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, Document, SystemMessage
from PIL import Image
from langchain_google_genai import ChatGoogleGenerativeAI
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory


logging.basicConfig(level=logging.DEBUG)

class PDFLoader:
    def __init__(self, model_name: str = "gemini-1.5-flash-8b"):
        self.llm = ChatGoogleGenerativeAI(
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

    def _gpt_ocr(self, image: Image.Image) -> str:
        try:
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

            response = self.llm.invoke(
                [
                    HumanMessage(
                        content=[
                            {
                                "type" : "text",
                                "text" :"You are an OCR. Return the text in the image as it is, if there are math equations use LaTeX for them. Do not miss anything. You will return the text only. I want pure math LaTeX, not markdown LaTeX. I need text back. Do not miss anything. If there are images, add a description of the images or text from them as is. Do not miss any text get everything!"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{encoded_image}"
                                }
                            }
                        ]
                    )
                ]
            )
            return response.content
        except Exception as e:
            return str(e)

    def _process_page(self, image: Image.Image) -> str:
        return self._gpt_ocr(image)

    def load(self, pdf_path: str) -> List[Document]:
        # Convert PDF pages to images and store in a list
        with open(pdf_path, 'rb') as file:
            pdf = PdfReader(file)
            total_pages = len(pdf.pages)

        pages = [convert_from_path(pdf_path, first_page=i, last_page=i)[0] for i in range(1, total_pages + 1)]
        print(f"Loaded {len(pages)} pages")
        # Process pages concurrently
        with ThreadPoolExecutor() as executor:
            future_to_page = {executor.submit(self._process_page, page): i for i, page in enumerate(pages)}
            results = [""] * len(pages)

            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    results[page_num] = Document(page_content=future.result())
                except Exception as exc:
                    print(f"Page {page_num} generated an exception: {exc}")

        return results

if __name__ == "__main__":
    loader = PDFLoader()
    print(loader.load("/home/zain/Downloads/AI/PII_ S0022-3115(00)00723-6.pdf"))