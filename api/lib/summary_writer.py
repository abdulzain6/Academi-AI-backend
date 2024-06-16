import io
import logging
import os
import tempfile
from markdown import markdown
from typing import Type
from langchain.chat_models.base import BaseChatModel

from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
import pypandoc
from retrying import retry
from docx import Document
from docx.shared import RGBColor


class SummaryWriter:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def get_markdown(self, data: str, word_count: int, instructions: str) -> str:
        system_prompt = """
You are an AI designed to assist people in writing summaries.
You will generate a summary for a minimum {minimum_words} words.
Do not mention the parts of summary as headings. For example, dont say ## Body or ## Intro etc.
Use the features of markdown like headings, text formatting to make the document professional looking this will be stored as pdf (Important)
"""
        human_prompt = """Use the following data to write a summary:
===============
{data}
===============


You must Follow these instructions while writing the summary:
===============
{instructions}
===============


You must follow the word limit of {minimum_words} (Very important)
Do not explictly mention intro body conclusion, the output must be good so no changes need to be made
Lets think step by step, keeping in mind whats said above to generate the summary for the data provided it must be of {minimum_words} words.
Follow the limit, you gave too small before.

The summary in markdown (DO NOT RETURN ANY OTHER TEXT):"""   
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(template=system_prompt),
                HumanMessagePromptTemplate.from_template(template=human_prompt)
            ],
            input_variables=[
                "minimum_words",
                "data",
                "instructions"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)

        return chain.run(
            minimum_words=word_count,
            data=data,
            instructions=instructions
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
            pypandoc.convert_text(content, 'docx', format='md', outputfile=temp_file.name, sandbox=True)
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
    def get_content(self, data: str, word_count: int, instructions: str):
        word_count = max(word_count, 10)
        content = self.get_markdown(data, word_count, instructions)
        logging.info(f"Making pdf.")
        docx_bytes = self.html_to_docx_bytes(content)
        pdf_bytes = self.docx_bytes_to_pdf_bytes(docx_bytes)
        logging.info(f"Making docx.")
        return {
            "pdf" : pdf_bytes,
            "docx" : docx_bytes,
            "text" : content
        }

