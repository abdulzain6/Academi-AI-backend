import math
import random
import uuid

from concurrent.futures import ThreadPoolExecutor
from .database import FileDBManager
from .knowledge_manager import KnowledgeManager
from langchain.text_splitter import TokenTextSplitter
from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.output_parsers import PydanticOutputParser
from langchain.schema.language_model import BaseLanguageModel
from pydantic import BaseModel, Field
from typing import Any, List, Union
from enum import Enum


class Answer(BaseModel):
    answer: str = Field(
        ...,
        json_schema_extra={
            "description": "The correct answer or one of the correct answers for the question."
        },
    )
    reason_of_choice: str = Field(
        ..., json_schema_extra={"description": "The reason why the answer is correct"}
    )
    
class Option(BaseModel):
    option: str = Field(
        ...,
        json_schema_extra={
            "description": "One of the possible options for multiple-choice questions."
        },
    )

class QuestionType(str, Enum):
    MCQ = "MCQ"
    SHORT_ANSWER = "short_answer"
#    TRUE_FALSE = "true_false"

class ResultType(str, Enum):
    CORRECT = "CORRECT"
    WRONG = "WRONG"
    
class QuizQuestion(BaseModel):
    question: str = Field(
        ...,
        json_schema_extra={"description": "The question that needs to be answered."},
    )
    question_type: QuestionType = Field(
        ...,
        json_schema_extra={
            "description": "The type of the question (MCQ, short_answer, true_false)."
        },
    )
    answer: Union[Answer, List[Answer]] = Field(
        ...,
        json_schema_extra={
            "description": "The correct answer or a list of correct answers."
        },
    )
    options: List[Option] = Field(
        default_factory=list,
        json_schema_extra={
            "description": "A list of options for multiple-choice questions. Optional and only relevant for MCQs."
        },
    )
    
class UserResponse(BaseModel):
    user_answer: str
    correct_answer: str
    reason_of_choice: str
    question: str
    id: str
    question_type: QuestionType
    
class QuestionResult(BaseModel):
    question_id: str
    reason_of_choice: str  = Field(
        ..., json_schema_extra={"description": "The reason why the answer is correct"}
    )
    result: ResultType
    correct_answer: str
    user_answer: str
    question: str

class QuestionResults(BaseModel):
    results: list[QuestionResult]

class Result(BaseModel):
    results: list[QuestionResult]
    score_percentage: float
    correct_answers: int
    total_answers: int 

class Quiz(BaseModel):
    questions: list[QuizQuestion] = Field(
        default_factory=list,
        json_schema_extra={"description": "THe list of questions for the quiz"},
    )

class QuizQuestionResponse(QuizQuestion):
    id: str

class QuizGenerator:
    def __init__(
        self,
        file_manager: FileDBManager,
        knowledge_manager: KnowledgeManager,
        llm: BaseLanguageModel,
        llm_kwargs: dict,
        chunk_size: int = 1500,
    ) -> None:
        self.file_manager = file_manager
        self.knowledge_manager = knowledge_manager
        self.chunk_size = chunk_size
        self.llm = llm
        self.llm_kwargs = llm_kwargs

    def run_chain(self, chain, text, number_of_questions: int) -> List[QuizQuestion]:
        output: Quiz = chain.run(data=text, number_of_questions=number_of_questions)
        return output.questions

    def generate_quiz(self, data: str, number_of_questions: int, max_generations: int = 5, collection_name: str = "Anything") -> list[QuizQuestionResponse]:
        text_splitter = TokenTextSplitter(
            chunk_size=self.chunk_size, model_name="gpt-3.5-turbo"
        )
        splits = text_splitter.split_text(data)
        texts = self.pick_evenly_spaced_elements(splits, max_generations)
        parser = PydanticOutputParser(pydantic_object=Quiz)
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to generate a quiz from the data. 
You will generate a variety of question types. (IMportant)
You will not generate unimportant or incomplete questions.
You will not generate too many questions as this is not the full quiz but a part of it. (Important) 
The quiz is to be of {number_of_questions} questions. (Important)
You will follow the following schema and will not return anything else
The schema:
{format_instructions}
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here is the data used to generate the quiz
===========
{data}
===========

If there is no data, Use your knowledge to generate the quiz about {collection_name}. if you dont know about this, make a general quiz

The generated quiz in proper schema without useless and incomplete questions, while picking a variety of question types. You must follow the schema(Important):
"""
                ),
            ],
            input_variables=["data", "number_of_questions"],
            partial_variables={"format_instructions": parser.get_format_instructions(), "collection_name" : collection_name},
        )
        questions: List[QuizQuestion] = []
        chain = LLMChain(
            prompt=prompt_template,
            output_parser=parser,
            llm=self.llm(**self.llm_kwargs),
        )
        
        if len(texts) == 0:
            questions = self.run_chain(chain, "", min(number_of_questions, 10))
        else:
            with ThreadPoolExecutor(max_workers=len(texts)) as executor:
                futures = [executor.submit(self.run_chain, chain, text, (number_of_questions // len(texts)) + 1) for text in texts]
                for future in futures:
                    questions.extend(future.result())

        return [QuizQuestionResponse(**question.model_dump(), id=str(uuid.uuid4())) for question in questions[:number_of_questions]]
    
    def pick_evenly_spaced_elements(self, arr: List[Any], n: int) -> List[Any]:
        arr_length = len(arr)

        if n <= 0 or n > arr_length:
            return arr

        if arr_length <= n:
            return arr

        spacing = math.floor(arr_length / n)

        if spacing == 0:
            spacing = 1

        start_idx = random.randint(0, spacing - 1)
        picked_elements = [
            arr[start_idx + i * spacing]
            for i in range(n)
            if start_idx + i * spacing < arr_length
        ]
        random.shuffle(picked_elements)
        return picked_elements

    def format_user_responses(self, responses: List[UserResponse]) -> str:
        formatted_responses = []

        for idx, response in enumerate(responses):
            formatted_response = (
                f"Response {idx + 1}:\n"
                f"  Question ID: {response.id}\n"
                f"  Question: {response.question}\n"
                f"  User Answer: {response.user_answer}\n"
                f"  Correct Answer: {response.correct_answer}\n"
                f"  Why the answer is correct: {response.reason_of_choice}\n"
            )
            formatted_responses.append(formatted_response)

        return "\n".join(formatted_responses)
    
    def separate_responses_by_type(self, responses: List[UserResponse]) -> tuple[List[UserResponse], List[UserResponse]]:
        short_answer_responses = []
        other_responses = []

        for response in responses:
            if response.question_type == QuestionType.SHORT_ANSWER:
                short_answer_responses.append(response)
            else:
                other_responses.append(response)

        return short_answer_responses, other_responses
        
    def calculate_performance(self, results: List[QuestionResult]) -> tuple[float, int, int]:
        total_questions = len(results)
        correct_answers = sum(
            result.result == ResultType.CORRECT for result in results
        )
        percentage_correct = (correct_answers / total_questions) * 100 if total_questions > 0 else 0.0
        return percentage_correct, correct_answers, total_questions      
  
    def evaluate_quiz(self, user_answers: list[UserResponse]) -> Result:
        parser = PydanticOutputParser(pydantic_object=QuestionResults)
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to evaluate quiz answers. 
You must behave like a teacher, help the students learn.
You will not check word to word, which means even if the answers wording is a bit different but it means the same as correct answer it will be correct. (Important)
You will follow the following schema to return the result nothing else and will not return anything else
Only evaluate the questions given to you, dont return any extra
The schema:
{format_instructions}
"""
            ),
            HumanMessagePromptTemplate.from_template(
                """
Here is the correct answer with explanation and user response.
===========
{data}
===========
You will not check word to word, which means even if the answers wording is a bit different but it means the same as correct answer it will be correct. (Important)
The result for the quiz, You must follow the schema(Important):
    """
                ),
            ],
            input_variables=["data"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        chain = LLMChain(
            prompt=prompt_template,
            output_parser=parser,
            llm=self.llm(**self.llm_kwargs),
        )
        short_answers, rest_answers = self.separate_responses_by_type(user_answers)
        incoming_ids = {answer.id for answer in user_answers}

        results = []
        for answer in rest_answers:
            if answer.user_answer == answer.correct_answer:
                result = QuestionResult(question_id=answer.id, reason_of_choice=answer.reason_of_choice, result="CORRECT", correct_answer=answer.correct_answer, question=answer.question, user_answer=answer.user_answer)
            else:
                result = QuestionResult(question_id=answer.id, reason_of_choice=answer.reason_of_choice, result="WRONG", correct_answer=answer.correct_answer, question=answer.question, user_answer=answer.user_answer)
            
            results.append(result)

        if short_answers:
            short_answer_result: QuestionResults = chain.run(data=self.format_user_responses(short_answers))
            results.extend(short_answer_result.results)

        results = [result for result in results if result.question_id in incoming_ids]
        percentage_correct, correct_answers, total_questions = self.calculate_performance(results)

        return Result(results=results, score_percentage=percentage_correct, correct_answers=correct_answers, total_answers=total_questions)