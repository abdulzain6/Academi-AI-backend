import io
import os
import tempfile
from markdown import markdown
from langchain.chat_models.base import BaseChatModel
from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate
)
import pdfkit
import pypandoc
import logging
from docx import Document
from docx.shared import RGBColor
from retrying import retry





class ContentInput(BaseModel):
    topic: str
    instructions: str
    minimum_word_count: int
    negative_prompt: str
    to_generate: str


class Writer:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def get_markdown(self, word_count: int, content_input: ContentInput) -> str:
        prompt = """
You are an AI designed to assist people in writing {to_generate}.
You will generate an {to_generate} for a minimum {minimum_words} words.
Do not mention the parts of {to_generate} as headings. For example, dont say ## Body or ## Intro etc.
Use the features of markdown like headings, text formatting to make the document professional looking this will be stored as pdf (Important)

The user has given some instructions on how the {to_generate} should be. They are as follows:
{instructions}

Keep in mind to not do the following regarding the {to_generate}:
{negative_prompt}
 
it must be on {topic}

Do not explictly mention intro body conclusion, the output must be good so no changes need to be made.
Lets think step by step, keeping in mind whats said above to generate the '{to_generate}' for the '{topic}' it must be of {minimum_words} words.
The {to_generate} in markdown (DO NOT RETURN ANY OTHER TEXT):"""   

        prompt = PromptTemplate(
            template=prompt,
            input_variables=[
                "minimum_words",
                "instructions",
                "negative_prompt",
                "topic",
                "to_generate",
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)

        return chain.run(
            minimum_words=word_count,
            instructions=content_input.instructions,
            negative_prompt=content_input.negative_prompt,
            topic=content_input.topic,
            to_generate=content_input.to_generate,
        )


    def docx_bytes_to_pdf_bytes(self, docx_bytes: bytes) -> bytes:
        # Create a temporary file for the DOCX content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_docx:
            docx_path = temp_docx.name
            temp_docx.write(docx_bytes)

        try:
            # Convert the DOCX to PDF using pypandoc
            pdf_path = temp_docx.name.replace('.docx', '.pdf')
            pypandoc.convert_file(docx_path, 'pdf', outputfile=pdf_path, extra_args=["--pdf-engine=xelatex"])
            
            # Read the generated PDF file and return its bytes
            with open(pdf_path, 'rb') as pdf_file:
                pdf_bytes = pdf_file.read()
            return pdf_bytes
        except Exception as e:
            logging.error(f"Error {e}")
            raise e
        finally:
            os.remove(docx_path)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
    
    def html_to_docx_bytes(self, content: str) -> bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(content, 'docx', format='md', outputfile=temp_file.name)
            temp_file_path = temp_file.name

        doc = Document(temp_file_path)
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)  # RGB values for black

        file_obj = io.BytesIO()
        doc.save(file_obj)
        file_obj.seek(0)  # Reset the file pointer to the beginning of the file
        os.unlink(temp_file_path)  # Delete the temporary file
        return file_obj.read()

    @retry(stop_max_attempt_number=3)
    def get_content(self, content_input: ContentInput):
        content_input.minimum_word_count = max(content_input.minimum_word_count, 10)
        logging.info(f"Generating content for {content_input}.")
        content = self.get_markdown(word_count=content_input.minimum_word_count, content_input=content_input)
        logging.info(f"Making pdf for {content_input}.")
        docx_bytes = self.html_to_docx_bytes(content)
        pdf_bytes = self.docx_bytes_to_pdf_bytes(docx_bytes)
        logging.info(f"Making docx for {content_input}.")
        return {
            "pdf" : pdf_bytes,
            "docx" : docx_bytes,
            "text" : content
        }

