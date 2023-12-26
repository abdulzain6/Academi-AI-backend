import uuid

from .database import FileDBManager
from .knowledge_manager import KnowledgeManager
from langchain.chains import LLMChain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.output_parsers import PydanticOutputParser
from langchain.schema.language_model import BaseLanguageModel
from langchain.pydantic_v1 import BaseModel, Field
from pydantic import BaseModel as RealBaseModel
from pydantic import BaseModel, Field
from typing import List
from enum import Enum
from retrying import retry
from langchain.chains import create_extraction_chain_pydantic
from openai import BadRequestError


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
            "description": "The type of the question (MCQ, short_answer)."
        },
    )
    answer: Answer = Field(
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


class UserResponse(RealBaseModel):
    user_answer: str
    correct_answer: str
    reason_of_choice: str
    question: str
    id: str
    question_type: QuestionType


class QuestionResult(BaseModel):
    question_id: str
    reason_of_choice: str = Field(
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


class FlashCard(BaseModel):
    question: str = Field(
        ...,
        json_schema_extra={"description": "The question"},
    )
    answer: str = Field(
        ...,
        json_schema_extra={"description": "The correct answer for the question"},
    )


class FlashCards(BaseModel):
    flashcards: list[FlashCard] = Field(
        default_factory=list,
        json_schema_extra={"description": "THe list of flashcards"},
    )


class QuizGenerator:
    def __init__(
        self,
        file_manager: FileDBManager,
        knowledge_manager: KnowledgeManager,
        llm: BaseLanguageModel,
    ) -> None:
        self.file_manager = file_manager
        self.knowledge_manager = knowledge_manager
        self.llm = llm

    def run_chain(self, chain, text, number_of_questions: int) -> List[QuizQuestion]:
        output: Quiz = chain.run(data=text, number_of_questions=number_of_questions)
        return output.questions

    def run_chain_fc(self, chain, text, number_of_questions: int) -> List[FlashCard]:
        output: FlashCards = chain.run(
            data=text, number_of_questions=number_of_questions
        )
        return output.flashcards

    @retry(stop_max_attempt_number=3)
    def generate_quiz(
        self,
        data: str,
        number_of_questions: int,
        collection_name: str = "Anything",
        maximum_questions: int = 10,
        collection_description: str = "ANything",
    ) -> list[QuizQuestionResponse]:
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
Follow the schema provided to generate the quiz, failing to do so will raise an error. (Important!!)
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here is the data used to generate the quiz
===========
{data}
===========

You will follow the following schema and will not return anything else or an error will be raised

The schema:
{format_instructions}


The generated quiz in proper schema without useless and incomplete questions, while picking a variety of question types. You must follow the schema(Important)
Failure to follow schema causes error
THe quiz with all rules above followed:
"""
                ),
            ],
            input_variables=["data", "number_of_questions", "description"],
            partial_variables={
                "format_instructions": parser.get_format_instructions(),
                "collection_name": collection_name,
                "description": collection_description,
            },
        )
        questions: List[QuizQuestion] = []
        chain = LLMChain(
            prompt=prompt_template,
            output_parser=parser,
            llm=self.llm,
        )

        questions = self.run_chain(
            chain,
            data
            or f"Use your knowledge to generate the quiz about '{collection_name}' Description : {collection_description}. if you dont know about the term, make a general quiz",
            min(number_of_questions, maximum_questions),
        )

        return [
            QuizQuestionResponse(**question.dict(), id=str(uuid.uuid4()))
            for question in questions[:maximum_questions]
        ]

    def format_user_responses(self, responses: List[UserResponse]) -> str:
        formatted_responses = []

        for idx, response in enumerate(responses):
            formatted_response = (
                f"Response {idx + 1}:\n"
                f"  Question ID: {response.id}\n=======\n"
                f"  Question: {response.question}\n========\n"
                f"  User Answer (What the user answered): {response.user_answer}\n"
                f"  Correct Answer (What the actual answer was): {response.correct_answer}\n========\n"
                f"  Why the answer is correct (Why the actual answer is correct): {response.reason_of_choice}\n\n\n======================"
            )
            formatted_responses.append(formatted_response)

        return "\n".join(formatted_responses)

    def separate_responses_by_type(
        self, responses: List[UserResponse]
    ) -> tuple[List[UserResponse], List[UserResponse]]:
        short_answer_responses = []
        other_responses = []

        for response in responses:
            if response.question_type == QuestionType.SHORT_ANSWER:
                short_answer_responses.append(response)
            else:
                other_responses.append(response)

        return short_answer_responses, other_responses

    def calculate_performance(
        self, results: List[QuestionResult]
    ) -> tuple[float, int, int]:
        total_questions = len(results)
        correct_answers = sum(result.result == ResultType.CORRECT for result in results)
        percentage_correct = (
            (correct_answers / total_questions) * 100 if total_questions > 0 else 0.0
        )
        return percentage_correct, correct_answers, total_questions

    @retry(stop_max_attempt_number=3)
    def generate_flashcards(
        self,
        data: str,
        number_of_flashcards: int,
        collection_name: str = "Anything",
        maximium_flashcards: int = 10,
        collection_description: str = "Anything",
    ) -> list[FlashCard]:
        parser = PydanticOutputParser(pydantic_object=FlashCards)
        prompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to generate flashcards from the data. 
You will not generate unimportant or incomplete questions.
You will not generate too many questions as this is not the full set but a part of it. (Important) 
The flashcard set is to be of {number_of_questions} questions. (Important)
Follow the schema provided to generate the flashcards, failing to do so will raise an error. (Important!!)
Only return the json!!
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here is the data used to generate the flashcards
===========
{data}
===========

You will follow the following schema and will not return anything else
The schema:
{format_instructions}

The generated flashcards in proper schema. You must follow the schema and return json only!!:
"""
                ),
            ],
            input_variables=["data", "number_of_questions"],
            partial_variables={
                "format_instructions": parser.get_format_instructions(),
                "collection_name": collection_name,
                "description": collection_description,
            },
        )
        flashcards: List[FlashCard] = []

        try:
            chain = LLMChain(
                prompt=prompt_template,
                output_parser=parser,
                llm=self.llm,
                llm_kwargs={
                    "response_format": {
                        "type": "json_object",
                        "schema": FlashCards.model_json_schema(),
                    }
                },
            )
            flashcards = self.run_chain_fc(
                chain,
                data
                or f"Make flashcards about {collection_name}, {collection_description}, if it doesnt make sense make general flashcards on the world",
                min(number_of_flashcards, maximium_flashcards),
            )
        except BadRequestError as e:
            chain = LLMChain(
                prompt=prompt_template,
                output_parser=parser,
                llm=self.llm,
                llm_kwargs={
                    "response_format": {
                        "type": "json_object",
                    }
                },
            )
            flashcards = self.run_chain_fc(
                chain,
                data
                or f"Make flashcards about {collection_name}, {collection_description}",
                min(number_of_flashcards, maximium_flashcards),
            )

        return flashcards[:number_of_flashcards]

    @retry(stop_max_attempt_number=3)
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
Be lenient in your evaluation, dont be super strict
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
The result for the quiz, You must follow the schema(Important):
    """
                ),
            ],
            input_variables=["data"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        oaiprompt_template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to evaluate quiz answers. 
You must behave like a teacher, help the students learn.
You will not check word to word, which means even if the answers wording is a bit different but it means the same as correct answer it will be correct. (Important)
You will follow the following schema to return the result nothing else and will not return anything else
Only evaluate the questions given to you, dont return any extra
Be lenient in your evaluation, dont be super strict
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here is the correct answer with explanation and user response.
===========
{data}
===========
You will not check word to word, which means even if the answers wording is a bit different but it means the same as correct answer it will be correct
    """
                ),
            ],
            input_variables=["data"],
        )
        short_answers, rest_answers = self.separate_responses_by_type(user_answers)
        incoming_ids = {answer.id for answer in user_answers}

        results = []
        for answer in rest_answers:
            if answer.user_answer == answer.correct_answer:
                result = QuestionResult(
                    question_id=answer.id,
                    reason_of_choice=answer.reason_of_choice,
                    result="CORRECT",
                    correct_answer=answer.correct_answer,
                    question=answer.question,
                    user_answer=answer.user_answer,
                )
            else:
                result = QuestionResult(
                    question_id=answer.id,
                    reason_of_choice=answer.reason_of_choice,
                    result="WRONG",
                    correct_answer=answer.correct_answer,
                    question=answer.question,
                    user_answer=answer.user_answer,
                )

            results.append(result)

        try:
            raise Exception()
            chain_oai = create_extraction_chain_pydantic(
                QuestionResult, self.llm, oaiprompt_template
            )
            if short_answers:
                short_answer_result: list[QuestionResult] = chain_oai.run(
                    data=self.format_user_responses(short_answers) or "",
                )
                results.extend(short_answer_result)
        except Exception as e:
            #    logging.error(f"Error in oai chain {e}")
            chain = LLMChain(
                prompt=prompt_template,
                output_parser=parser,
                llm=self.llm,
            )
            if short_answers:
                short_answer_result: QuestionResults = chain.run(
                    data=self.format_user_responses(short_answers)
                )
                results.extend(short_answer_result.results)

        results = [result for result in results if result.question_id in incoming_ids]
        (
            percentage_correct,
            correct_answers,
            total_questions,
        ) = self.calculate_performance(results)

        return Result(
            results=results,
            score_percentage=percentage_correct,
            correct_answers=correct_answers,
            total_answers=total_questions,
        )
