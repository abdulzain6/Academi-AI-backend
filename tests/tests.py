#!/usr/bin/env python
from io import BufferedReader, BytesIO
import requests
import pytesseract
import json
from typing import Any, Optional, Union, Type
from PIL import Image
from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import ChatOpenAI


class ImageOCR:
    def __init__(self, app_id: str, app_key: str, llm_kwargs: dict, llm_cls: Type[BaseChatModel]) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.llm_kwargs = llm_kwargs
        self.llm = llm_cls(**llm_kwargs, temperature=0)

    def extract_text_with_tesseract(self, image_input: Union[str, Any]) -> Optional[str]:
        """
        Extract text from an image using Tesseract.

        Parameters:
            image_input (Union[str, Any]): The path to the image file or the image file object.

        Returns:
            Optional[str]: The extracted text, or None if an error occurs.
        """
        try:
            if isinstance(image_input, (str, BufferedReader)):
                image = Image.open(image_input)
            else:
                raise ValueError("Invalid input type. Provide either a file path or a file object.")

            return pytesseract.image_to_string(image)
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def extract_text_with_mathpix(self, image_input: Union[str, Any]) -> Optional[str]:
        """
        Extract text from an image using Mathpix API.

        Parameters:
            image_input (Union[str, Any]): The path to the image file or the image file object.

        Returns:
            Optional[str]: The extracted text, or None if an error occurs.
        """
        try:
            if isinstance(image_input, str):
                with open(image_input, "rb") as f:
                    image_bytes = f.read()
            elif isinstance(image_input, BufferedReader):
                image_bytes = BytesIO(image_input.read()).getvalue()
            else:
                raise ValueError("Invalid input type. Provide either a file path or a file object.")
            
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
        system_prompt = """
You are to look at two ocrs for a maths/physics problem one from tesseract and mathpix, both have drawbacks.
So look at both the ocrs and construct a final piece that uses both of the ocrs to create a perfect result.
Return the cleaned result nothing else.
Return latex in good form.
        """
        prompt = """
Following is a maths/physics question extracted using tesseract ocr:
{tesseract_text}

Following is a maths question extracted using mathpix ocr:
{mathpix_text}

The cleaned text after looking at both ocrs, No other text:"""

        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(system_prompt),
                HumanMessagePromptTemplate.from_template(prompt)
            ],
            input_variables=["tesseract_text", "mathpix_text"]
        )
        chain = LLMChain(llm=self.llm, prompt=prompt_template)
        return chain.run(tesseract_text=tesseract_text, mathpix_text=mathpix_text)

    def ocr_image(self, image_input: Union[str, Any]) -> Optional[str]:
        tesseract_text = self.extract_text_with_tesseract(image_input)
        mathpix_text = self.extract_text_with_mathpix(image_input)
        return self.extract_clean_text(mathpix_text, tesseract_text)



if __name__ == "__main__":
    import langchain
    langchain.verbose = True
    image_ocr = ImageOCR(app_id="aiinnovate_ffb9d0_12bf4f",
                         app_key="3c960a40415cd4b7675d13008c9d3e7a2c74fd3979ce857b5cef1bc423490fc2",
                         llm_kwargs={"openai_api_key": "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"},
                         llm_cls=ChatOpenAI)
    print(image_ocr.ocr_image("/home/zain/Downloads/WhatsApp Image 2023-09-18 at 2.44.14 PM.jpeg"))