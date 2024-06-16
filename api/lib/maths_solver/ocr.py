from io import BytesIO
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import base64
from PIL import Image



class ImageOCR:        
    def gemini_ocr(self, image_path: str) -> str:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest")

        with Image.open(image_path) as img:
        # Convert the image to PNG format
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        response = llm.invoke(
            [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "You are an OCR, Return the text in the image as it is, if there are maths equations use latex for them. Do not miss anything. You will return the text only. I want pure math latex not markdown latex. I need text back",
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
        print(response)
        return response.content

    def ocr_image(self, image_input: str) -> Optional[str]:
        return self.gemini_ocr(image_input)