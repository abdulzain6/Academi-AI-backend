import requests
import pytesseract
import json
from typing import Any, Optional, Union, Type, BinaryIO
from PIL import Image
from langchain.chains import LLMChain
from langchain.prompts import (
    PromptTemplate
)
from io import BufferedReader, BytesIO
from langchain.chat_models.base import BaseChatModel


class ImageOCR:
    def __init__(self, app_id: str, app_key: str, llm_kwargs: dict, llm_cls: Type[BaseChatModel]) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.llm_kwargs = llm_kwargs
        self.llm = llm_cls(**llm_kwargs, temperature=0)

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
                
            r = requests.post("https://api.mathpix.com/v3/text",
                              files={"file": image_bytes},
                              data={
                                  "options_json": json.dumps({
                                      "math_inline_delimiters": ["$", "$"],
                                      "rm_spaces": True
                                  })
                              },
                              headers={
                                  "app_id": self.app_id,
                                  "app_key": self.app_key
                              }
                             )
            return r.json().get("text", None)
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def extract_clean_text(self, mathpix_text: str, tesseract_text: str) -> Optional[str]:
        prompt = """
You are to look at two ocrs for a maths/physics problem one from tesseract and mathpix, both have drawbacks.
So look at both the ocrs and construct a final piece that uses both of the ocrs to create a perfect result.
Return the cleaned result nothing else.
Return latex in good form.

Following is a maths/physics question extracted using tesseract ocr:
{tesseract_text}

Following is a maths question extracted using mathpix ocr:
{mathpix_text}

The cleaned text after looking at both ocrs, No other text:"""

        prompt_template = PromptTemplate(
            template=prompt,
            input_variables=["tesseract_text", "mathpix_text"]
        )
        chain = LLMChain(llm=self.llm, prompt=prompt_template)
        return chain.run(tesseract_text=tesseract_text, mathpix_text=mathpix_text)

    def ocr_image(self, image_input: str) -> Optional[str]:
        tesseract_text = self.extract_text_with_tesseract(image_input)
        mathpix_text = self.extract_text_with_mathpix(image_input)
        print("Tesseract text: ", tesseract_text, "Mathpix Text:", mathpix_text)
        if tesseract_text or mathpix_text:
            return self.extract_clean_text(mathpix_text, tesseract_text)
        else:
            raise ValueError("Image has no text")

