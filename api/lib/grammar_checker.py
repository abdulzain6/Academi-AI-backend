import logging
from typing import List
from langchain.chat_models.base import BaseChatModel
from langchain.chains import LLMChain
from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

class GrammarIssue(BaseModel):
    problematic_part: str = Field(json_schema_extra={"description" : "The problematic part in the text. This must be exactly same as from the text."})
    corrected_text: str = Field(json_schema_extra={"description" : "The corrected replacement for the problematic part."})
    what_the_issue_was: str = Field(json_schema_extra={"description" : "Why the part was wrong. What the grammar mistake was"})
    
class GrammarIssues(BaseModel):
    grammar_issues: List[GrammarIssue] = Field(json_schema_extra={"description" : "The grammar issues in the provided text."})
    corrected_text: str = Field(json_schema_extra={"description" : "The corrected text with issues fixed."})
    
class GrammarChecker:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
        
    def check_grammar(self, text: str) -> dict:
        parser = PydanticOutputParser(pydantic_object=GrammarIssues)
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to detect and correct grammar issues or any language issues from text.
You must check the complete text.
You will return json in the schema told to you (Important).
If there is no issue return an empty list (IMportant)
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """Look at the following text for grammar issues and any other language issues:
===========
{data}
============

The issues must be formatted in the schema below:
{format_instructions}
=====================

If there is no issue return an empty list (IMportant)
Dont use invalid escapes!
Before outputting, you must check if the text your about to output is valid or not.
Lets think step by step, Correcting an issue may raise a new one. so fix recursively.
The issues in proper format (Failure causes big error):"""
                ),
            ],
            input_variables=[
                "data",
            ],
            partial_variables={"format_instructions" : parser.get_format_instructions()}
        )
        chain = LLMChain(prompt=prompt, llm=self.llm, output_parser=parser)
        for _ in range(3):
            try:
                issues: GrammarIssues = chain.run(data=text)
                break
            except Exception as e:
                logging.error(f"Error in grammar checker {e}")
            
        return {"issues" : issues.model_dump()}
        
