from langchain.llms import OpenAI
from langchain.llms.base import BaseLLM
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from models import CourseCurriculum, StudentCurriculumInput


class CurriculumGenerator:
    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def generate_curriculum(
        self, student_input: StudentCurriculumInput
    ) -> CourseCurriculum:
        template = """
You are an AI teacher, You will teach students in an academy.
You are to design a course curriculum for a student.

The student has provided the following details:
{student_details}

Lets think step by step, to generate a course curriculum for the student. 

You must follow the following schema:
{format_instructions}

The curriculum:"""
        output_parser = PydanticOutputParser(pydantic_object=CourseCurriculum)
        chain = LLMChain(
            prompt=PromptTemplate(
                template=template,
                input_variables=["student_details"],
                partial_variables={
                    "format_instructions": output_parser.get_format_instructions()
                },
            ),
            llm=self.llm,
            output_parser=output_parser,
        )
        return chain.run(student_input.format_for_ai())


if __name__ == "__main__":
    import langchain
    langchain.verbose = True
    generator = CurriculumGenerator(
        OpenAI(
            model="gpt-3.5-turbo-instruct",
            temperature=0,
            max_tokens=2000,
            request_timeout=100,
            openai_api_key="",
        )
    )
    curr = generator.generate_curriculum(StudentCurriculumInput(course_name="Calculus"))
    print(curr)