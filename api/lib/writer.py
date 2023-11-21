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
The {to_generate} in markdown:"""   

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

    def generate_content_html(self, content_input: ContentInput) -> tuple[str, str]:
        content = self.get_markdown(word_count=content_input.minimum_word_count, content_input=content_input)
        return markdown(content), content
    
    def html_to_pdf_bytes(self, html: str) -> bytes:
        return pdfkit.from_string(html, False)
    
    def html_to_docx_bytes(self, html: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".docx") as tmpfile:
            pypandoc.convert_text(html, 'docx', format='html', outputfile=tmpfile.name)
            tmpfile.seek(0)
            docx_bytes = tmpfile.read()
        return docx_bytes
    
    @retry(stop_max_attempt_number=3)
    def get_content(self, content_input: ContentInput):
        content_input.minimum_word_count = max(content_input.minimum_word_count, 10)
        logging.info(f"Generating content for {content_input}.")
        html, text = self.generate_content_html(content_input)
        logging.info(f"Making pdf for {content_input}.")
        pdf_bytes = self.html_to_pdf_bytes(html)
        logging.info(f"Making docx for {content_input}.")
        docx_bytes = self.html_to_docx_bytes(html)
        return {
            "pdf" : pdf_bytes,
            "docx" : docx_bytes,
            "text" : text
        }

