import tempfile
from markdown import markdown
from typing import Type
from langchain.chat_models.base import BaseChatModel
from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
import pdfkit
import pypandoc
from retrying import retry



class Content(BaseModel):
    content_markdown: str = Field(json_schema_extra={"description": "The content for the user requested material"})


class SummaryWriter:
    def __init__(self, llm: Type[BaseChatModel], llm_kwargs: dict) -> None:
        self.llm = llm
        self.llm_kwargs = llm_kwargs

    def get_markdown(self, data: str, word_count: int) -> Content:
        parser = PydanticOutputParser(pydantic_object=Content)
        system_prompt = """
You are an AI designed to assist people in writing summaries.
You will generate a summary for a minimum {minimum_words} words.
You must follow the schema return nothing else.
Do not mention the parts of summary as headings. For example, dont say ## Body or ## Intro etc.
Use the features of markdown like headings, text formatting to make the document professional looking this will be stored as pdf (Important)
"""
        human_prompt = """Use the following data to write a summary:
===============
{data}
===============

Schema:
======================
{format_instructions}
=======================

You must follow the word limit of {minimum_words} (Very important)
Do not explictly mention intro body conclusion, the output must be good so no changes need to be made
Lets think step by step, keeping in mind whats said above to generate the summary for the data provided it must be of {minimum_words} words.
Follow the schema above (Important) Make sure the json is correct!
Follow the limit, you gave too small before.
"""   
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(template=system_prompt),
                HumanMessagePromptTemplate.from_template(template=human_prompt)
            ],
            input_variables=[
                "minimum_words",
                "data",
            ],
            partial_variables={"format_instructions" : parser.get_format_instructions()}
        )
        chain = LLMChain(prompt=prompt, llm=self.llm(**self.llm_kwargs), output_parser=parser, verbose=True)

        return chain.run(
            minimum_words=word_count,
            data=data
        )

    def generate_content_html(self, data: str, word_count: int) -> tuple[str, str]:
        #plan = self.get_content_plan(content_input)
        content = self.get_markdown(data, word_count)
        return markdown(content.content_markdown), content.content_markdown
    
    def html_to_pdf_bytes(self, html: str) -> bytes:
        return pdfkit.from_string(html, False)
    
    def html_to_docx_bytes(self, html: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".docx") as tmpfile:
            pypandoc.convert_text(html, 'docx', format='html', outputfile=tmpfile.name)
            tmpfile.seek(0)
            docx_bytes = tmpfile.read()
        return docx_bytes
    
    @retry(stop_max_attempt_number=3)
    def get_content(self, data: str, word_count: int):
        html, text = self.generate_content_html(data, word_count)
        pdf_bytes = self.html_to_pdf_bytes(html)
        docx_bytes = self.html_to_docx_bytes(html)
        return {
            "pdf" : pdf_bytes,
            "docx" : docx_bytes,
            "text" : text
        }

