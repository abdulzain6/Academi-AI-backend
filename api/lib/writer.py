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

class GenerationPlan(BaseModel):
    plan: str = Field(
        json_schema_extra={"description": "A plan that can be used to write the content"}
    )  

class ContentInput(BaseModel):
    topic: str
    instructions: str
    minimum_word_count: int
    negative_prompt: str
    to_generate: str


class Writer:
    def __init__(self, llm: Type[BaseChatModel], llm_kwargs: dict) -> None:
        self.llm = llm
        self.llm_kwargs = llm_kwargs

    def get_content_plan(self, content_input: ContentInput) -> GenerationPlan:
        parser = PydanticOutputParser(pydantic_object=GenerationPlan)
        system_prompt = """
You are an AI designed to assist students in writing {to_generate}.
You are to plan an {to_generate} on {topic}. 
You will generate a plan that is enough to form an {to_generate} of a minimum of {minimum_words} words.
Start with an introduction to the topic and with a conclusion (important)
Be super short 20 words only!! (Important).
You must follow the schema return nothing else.
"""
        human_prompt = """
The student has given some instructions on how the {to_generate} should be. They are as follows:
{instructions}

Keep in mind to not do the following regarding the {to_generate}:
{negative_prompt}


Schema:
======================
{format_instructions}
=======================

Lets think step by step, keeping in mind whats said above to generate the plan that can be used to write the {to_generate}.
Be super short 20 words only!! (Important).
Follow the schema above (Important)
"""
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(template=system_prompt),
                HumanMessagePromptTemplate.from_template(template=human_prompt)
            ],
            input_variables=[
                "minimum_words",
                "to_generate",
                "topic",
                "instructions",
                "negative_prompt",
            ],
            partial_variables={"format_instructions" : parser.get_format_instructions()}
        )
        chain = LLMChain(prompt=prompt, llm=self.llm(**self.llm_kwargs), output_parser=parser)
        return chain.run(
            minimum_words=content_input.minimum_word_count,
            topic=content_input.topic,
            instructions=content_input.instructions,
            negative_prompt=content_input.negative_prompt,
            to_generate=content_input.to_generate
        )

    def get_markdown(self, plan: GenerationPlan, word_count: int, content_input: ContentInput) -> Content:
        parser = PydanticOutputParser(pydantic_object=Content)
        system_prompt = """
You are an AI designed to assist people in writing {to_generate}.
You will generate an {to_generate} for a minimum {minimum_words} words.
You must follow the schema return nothing else.
Follow the plan to write the {to_generate}
Do not mention the parts of {to_generate} as headings. For example, dont say ## Body or ## Intro etc.
Use the features of markdown like headings, text formatting to make the document professional looking this will be stored as pdf (Important)
"""
        human_prompt = """
The user has given some instructions on how the {to_generate} should be. They are as follows:
{instructions}

Keep in mind to not do the following regarding the {to_generate}:
{negative_prompt}

Schema:
======================
{format_instructions}
=======================

You are writing an {to_generate} on {topic}.
Here is the plan you can use to write it:
{plan}
 

Do not explictly mention intro body conclusion, the output must be good so no changes need to be made
Lets think step by step, keeping in mind whats said above to generate the {to_generate} for the {topic} it must be of {minimum_words} words.
Follow the schema above (Important) Make sure the json is correct!
"""   
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(template=system_prompt),
                HumanMessagePromptTemplate.from_template(template=human_prompt)
            ],
            input_variables=[
                "minimum_words",
                "instructions",
                "negative_prompt",
                "topic",
                "to_generate",
                "plan"
            ],
            partial_variables={"format_instructions" : parser.get_format_instructions()}
        )
        chain = LLMChain(prompt=prompt, llm=self.llm(**self.llm_kwargs), output_parser=parser)

        return chain.run(
            minimum_words=word_count,
            instructions=content_input.instructions,
            negative_prompt=content_input.negative_prompt,
            topic=content_input.topic,
            to_generate=content_input.to_generate,
            plan=plan.plan
        )

    def generate_content_html(self, content_input: ContentInput) -> tuple[str, str]:
        #plan = self.get_content_plan(content_input)
        content = self.get_markdown(GenerationPlan(plan="Use your brain"), content_input.minimum_word_count, content_input)
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
    def get_content(self, content_input: ContentInput):
        html, text = self.generate_content_html(content_input)
        pdf_bytes = self.html_to_pdf_bytes(html)
        docx_bytes = self.html_to_docx_bytes(html)
        return {
            "pdf" : pdf_bytes,
            "docx" : docx_bytes,
            "text" : text
        }

