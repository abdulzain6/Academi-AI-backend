import re
import tempfile
import pypandoc
import os
import io
from langchain.pydantic_v1 import BaseModel, Field
from docx import Document
from docx.shared import RGBColor
from langchain.chat_models.base import BaseChatModel
from langchain.schema import SystemMessage, HumanMessage
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chains import LLMChain
from .base import NotesMaker

class MarkdownData(BaseModel):
    content: str = Field(json_schema_extra={"description" : "The notes content in markdown format"})

class Title(BaseModel):
    title: str

class MarkdownNotesMaker(NotesMaker):
    def __init__(self, llm: BaseChatModel, **kwargs):
        self.llm = llm

    @staticmethod
    def get_schema():
        return MarkdownData.model_json_schema()
    
    def make_notes_from_dict(self, data_dict: str) -> io.BytesIO:
        input_data = MarkdownData.model_validate(data_dict)
        return self.make_notes(input_data.content, context=None)
        
    def make_notes_from_string(self, string: str, instructions: str) -> io.BytesIO:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to make Text notes from text.
You must also follow the instructions given to you
Only answer from the notes given to you. No making things up
You must pick every minute detail.
You will return the notes in markdown
You must make super detailed and lenghty notes
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Use the following data to make the notes:
{data}
============

Follow the instructions below also:
============
{instructions}
============

The notes in markdown (RETURN NO OTHER TEXT):"""
                ),
            ],
            input_variables=[
                "data",
                "instructions"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)
        notes = chain.run(data=string, instructions=instructions)
        return self.make_notes(data=MarkdownData(content=notes))

    def make_notes_from_string_return_string_only(self, string: str, instructions: str) -> str:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to make notes from text.
You must also follow the instructions given to you
Only answer from the notes given to you. No making things up
You must pick every minute detail.
You will return the notes in markdown
You must make super detailed and lenghty notes
Only return markdown content dont put inside of markdown block just return content.
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Use the following data to make the notes:
{data}
============

Follow the instructions below also:
============
{instructions}
============

The notes in markdown (RETURN NO OTHER TEXT):"""
                ),
            ],
            input_variables=[
                "data",
                "instructions"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)
        notes = chain.run(data=string, instructions=instructions)
    
        # Extract content from markdown code blocks
        code_block_pattern = r'```(?:markdown)?\s*([\s\S]*?)\s*```'
        code_blocks = re.findall(code_block_pattern, notes, re.IGNORECASE)
        
        if code_blocks:
            # Join all extracted code blocks
            extracted_content = '\n\n'.join(code_blocks)
            return extracted_content.strip()
        else:
            # If no code blocks found, return the original notes
            return notes.strip()
        
    def generate_title(self, content: str) -> str:
        structured_llm = self.llm.with_structured_output(Title)
        return structured_llm.invoke(
            [
                SystemMessage(
                    content="Your purpose is to generate one line title from the notes given to you."
                ),
                HumanMessage(content=f"Genrate a one line title for the following text: \n{content}")
            ]
        ).title
        
    def make_notes_from_string_return_string(self, string: str, instructions: str) -> tuple[str, io.BytesIO]:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to make notes from text.
You must also follow the instructions given to you
Only answer from the notes given to you. No making things up
You must pick every minute detail.
You will return the notes in markdown
You must make super detailed and lenghty notes
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Use the following data to make the notes:
{data}
============

Follow the instructions below also:
============
{instructions}
============

The notes in markdown (RETURN NO OTHER TEXT):"""
                ),
            ],
            input_variables=[
                "data",
                "instructions"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)
        notes = chain.run(data=string, instructions=instructions)
        return notes, self.make_notes(data=MarkdownData(content=notes))
        
    def make_notes(self, data: MarkdownData, context: None = None):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(data.content, 'docx', format='md', outputfile=temp_file.name, sandbox=True)
            temp_file_path = temp_file.name

        # Open the generated DOCX file with python-docx
        doc = Document(temp_file_path)

        # Iterate through paragraphs and set text color to black
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)  # RGB values for black

        # Save the modified DOCX content to a BytesIO object
        file_obj = io.BytesIO()
        doc.save(file_obj)
        file_obj.seek(0)  # Reset the file pointer to the beginning of the file

        os.unlink(temp_file_path)  # Delete the temporary file

        return file_obj

