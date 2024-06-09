from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain.schema import HumanMessage


class ImageOCR:        
    def gemini_ocr(self, image_path: str) -> str:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", safety_settings = {
                HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            })
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