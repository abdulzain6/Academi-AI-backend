import base64
import io
import logging
import os
import re
import subprocess
import tempfile
import pypandoc
import os
import shutil
from docx import Document
from docx.shared import Inches
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder
)
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.schema import SystemMessage, HumanMessage
from langchain.pydantic_v1 import BaseModel, Field, validator
from docx.shared import RGBColor
from docx.enum.shape import WD_INLINE_SHAPE_TYPE

from typing import Optional
from pdf2image import convert_from_path
from langchain.chat_models.base import BaseChatModel
from PIL import Image, ImageDraw, ImageFont
from langchain_core.tools import tool
from concurrent.futures import ThreadPoolExecutor, as_completed


class Question(BaseModel):
    question_to_solve_markdown: str = Field(description="The question/Task mentioned in the assignment for the student to do. Must be word to word in markdown!. Must be clean and readable adjust if needed.")
    question_number: str = Field(default="Q",description="The question/Task number, Defaults to 'Q.'")    
    page_numbers: Optional[list[int]] = Field(None, description="The page numbers the question is on, Its written on the top in purple. If question is spread across pages return all the page numbers its on. Include the pages with diagrams related to the questions also")
    requires_seeing: bool = Field(description="Whether the user needs to see the question to understand (Diagrams etc). Should be false if access to the qustion text is enough")

    @validator('question_to_solve_markdown', pre=True, each_item=False)
    def extract_code_block(cls, v):
        # Regular expression to find code blocks wrapped with triple backticks
        code_blocks = re.findall(r'```[\w\s]*\n(.*?)```', v, re.DOTALL)
        if code_blocks:
            # Join multiple code blocks with a newline
            return '\n\n'.join(code_blocks).strip()
        return v  # Return original if no code blocks are found

class Questions(BaseModel):
    questions_or_tasks: list[Question]
    assignment_topic: str
    
class Solution(BaseModel):
    solution_markdown: str = Field(description="The complete Solution to the question from start to finish in markdown in full detail. This will be directly put into the assignment so Get straight to the answer, do not add phrases like 'To solve the question'")

    @validator('solution_markdown', pre=True, each_item=False)
    def extract_code_block(cls, v):
        # Similar regular expression as used for Question
        code_blocks = re.findall(r'```[\w\s]*\n(.*?)```', v, re.DOTALL)
        if code_blocks:
            # Join multiple code blocks with a newline
            return '\n\n'.join(code_blocks).strip()
        return v  # Return original if no code blocks are found
    
class AssignmentSolver:
    def __init__(self, llm_extractor: BaseChatModel, llm_solver: BaseChatModel, solver_tools: list, last_page: int = 3) -> None:
        self.llm_extractor = llm_extractor
        self.last_page = last_page
        self.llm_solver = llm_solver
        self.solver_tools = solver_tools
        
    def set_tools(self, tools: list):
        self.solver_tools = tools
        
    def solve_question(self, question, images, instructions: str):
        #output_parser = OutputFixingParser.from_llm(
        #    parser=PydanticOutputParser(pydantic_object=Solution), llm=self.llm_solver
        #)
        if instructions:
            instructions_message = f"""The student has also given the following instructions, so follow them:
    {instructions}
            """
        else:
            instructions_message = ""
        sys_template = f"""
You are an AI designed to solve assignments you will use tools to better answer the question.
Rules:
    1. Use latex for maths equations
    2. Avoid writing the question again in the solution as that is already in the assignment. 
    3. When you include a link/Diagram make sure to show it. like this ![This is an image](https://example.com/path/to/image.jpg)
    4. Do not put json in the solution. It must be markdown and readable.
    5. You must solve the question, not just provide the steps. You need to provide full implementation
    6. Use tools to better answer the question. (Important)
    7. Its always good to add diagrams where applicable.
    8. Get straight to the answer, do not add phrases like "To solve the question"
    9. Do not sound like an AI.
    10. Dont add random links to the solution only add those returned by the tools if any
    11. Dont make links up!!!!
    12. DONT ADD CODE TO THE SOLUTION UNLESS ASKED!!, tHIS IS FOR AN ASSIGNMENT. why you so dumb>>?
    14. your response will be directly put into an assignment. We dont want links in there you need to add the links in a way its visible like shown above also dont add useless text ffs
    15. Also if you decide to generate a diagram dont say they are 'generated'.
    13  MAKE SURE TO call tools in proper json, Remeber json doesnt support single quotes.!!
    
{instructions_message}

FOLLOW ALL ABOVE RULES! 
"""

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=sys_template),
                MessagesPlaceholder(variable_name='input'),
                MessagesPlaceholder(variable_name='agent_scratchpad'),
            ]
        )
        agent = create_tool_calling_agent(self.llm_solver, self.solver_tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=self.solver_tools, verbose=True, handle_parsing_errors=True, max_iterations=5)

        if question.requires_seeing:
            question_images = [images[page_number - 1] for page_number in question.page_numbers]
        else:
            question_images = []

        formatted_images = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}", "detail": "low"}}
            for image in question_images
        ]

        message = HumanMessage(
            content=[
                {"type": "text", "text": f"Solve the following question:\n{question.question_to_solve_markdown}\n Dont make links up only use links from tools\n your response will be directly put into an assignment.\n The answer in markdown, get straight to it no phrases like 'To solve this question':"},
                *formatted_images
            ]
        )

        result = agent_executor.invoke({"input": [message]})
        return Solution(solution_markdown=result.get('output'))
      #  return result.get("output", "[]")

    def solve_questions(self, questions: Questions, images: list[str], instructions: str, max_questions: int = 10) -> list[Solution]:
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Start all tasks and mark each future with its question index
            futures = [executor.submit(self.solve_question, question, images, instructions) for question in questions.questions_or_tasks[:max_questions]]
            # Collect results as they complete
            results = [future.result() for future in as_completed(futures)]
        return results
        
    @staticmethod # handle images manually using docx
    def markdown_to_docx(content: str) -> bytes:
        link_pattern = re.compile(r'\[([^\]]+)\]\((file://[^\)]+)\)')
        img_pattern = re.compile(r'!\[([^\]]*)\]\((file://[^\)]+)\)')

        # Replace local file paths in links and images with placeholders
        content = link_pattern.sub(r'[\1](#)', content)
        content = img_pattern.sub(r'![\1](#)', content)
        
        # Convert markdown content to a .docx file using a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(content.replace("https", "http"), 'docx', format='md', outputfile=temp_file.name)
            temp_file_path = temp_file.name

        # Open the temporary .docx file with python-docx
        doc = Document(temp_file_path)

        # Iterate through all paragraphs to set text color
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)  # RGB values for black

        # Resize images maintaining aspect ratio within specified limits
        image_types = {WD_INLINE_SHAPE_TYPE.LINKED_PICTURE, WD_INLINE_SHAPE_TYPE.PICTURE}
        for shape in doc.inline_shapes:
            # Check if shape is a picture type
            if shape.type in image_types:
                original_width = shape.width.inches
                original_height = shape.height.inches
                logging.debug(f'Original size: {original_width} x {original_height} inches.')

                # Ensure both dimensions are within the 1 to 3 inches range
                while shape.width.inches > 3 or shape.height.inches > 5:
                    shape.width = Inches(shape.width.inches / 2)
                    shape.height = Inches(shape.height.inches / 2)
                    logging.debug(f'Resized to: {shape.width.inches} x {shape.height.inches} inches.')

                # Ensure neither dimension falls below 1 inch, if possible without exceeding 3 inches
                while shape.width.inches < 1 and shape.height.inches * 2 <= 5:
                    shape.width = Inches(shape.width.inches * 2)
                    shape.height = Inches(shape.height.inches * 2)
                    logging.debug(f'Adjusted size: {shape.width.inches} x {shape.height.inches} inches.')

        # Write the modified content to a BytesIO object
        file_obj = io.BytesIO()
        doc.save(file_obj)
        file_obj.seek(0)  # Reset the file pointer to the beginning of the file
        os.unlink(temp_file_path)  # Delete the temporary file

        return file_obj.read()

    def extract_questions(self, doc_path: str) -> tuple[Questions, list[str]]:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf_file:
            temp_pdf_path = temp_pdf_file.name
        
        try:
            self.convert_to_pdf(doc_path, temp_pdf_path)
            base64_images = self.pdf_to_base64_images(temp_pdf_path)
            assert len(base64_images) <= self.last_page, f"File is too large to process. Try another one. Max pages: {self.last_page}, Used: {len(base64_images)}"
            
            formatted_images = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image}",  # noqa: E501
                        "detail": "low"
                    }
                }
                for image in base64_images
            ]
            
            output_parser = OutputFixingParser.from_llm(
                parser=PydanticOutputParser(pydantic_object=Questions), llm=self.llm_extractor
            )
            human_message = HumanMessage(
                content=[
                    *formatted_images, 
                    {"type": "text", "text": f"""Extract the questions from the images provided, Use latex for maths equations"""},
                ]
            )   
            sys_template = f"""
You are an AI designed to extract questions/ Tasks from assignments so they can be solved.
Extract them in proper format.
Use latex for maths equations
Only extract the questions/Tasks if they are mentioned explictly (Important)
            """
            prompt = ChatPromptTemplate.from_messages(
                [
                    SystemMessage(content=sys_template),
                    MessagesPlaceholder(variable_name='input'),
                ]
            )
            runnable = prompt | self.llm_extractor.with_structured_output(schema=Questions)
            return runnable.invoke({"input": [human_message]}), base64_images
            #return output_parser.parse(runnable.invoke({"input": [human_message]}).content), base64_images
        finally:
            os.remove(temp_pdf_path)

    def convert_to_pdf(self, input_path: str, output_path: str) -> None:
        """
        Convert a PDF, DOCX, or TXT file to a PDF.

        :param input_path: Path to the input file.
        :param output_path: Path to the output PDF file.
        """
        file_extension = os.path.splitext(input_path)[1].lower()

        if file_extension == ".pdf":
            shutil.copyfile(input_path, output_path)
        elif file_extension in [".docx", ".txt"]:
            self.convert_docx_or_txt_to_pdf(input_path, output_path, file_extension)
        else:
            raise ValueError("Unsupported file type. Supported types are: PDF, DOCX, TXT.")

    @staticmethod
    def convert_docx_or_txt_to_pdf(input_path: str, output_path: str, file_extension: str):
        libre_office_path = '/usr/bin/libreoffice'  # Path to the LibreOffice executable
        output_dir = os.path.dirname(output_path)  # Extract directory from the output path
        temp_pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(input_path))[0] + '.pdf')

        # Run LibreOffice to convert the file to PDF in the specified directory
        subprocess.run([
            libre_office_path, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, input_path
        ], check=True)

        # Move the temporary PDF file to the desired output path if it's not already correct
        if temp_pdf_path != output_path:
            os.rename(temp_pdf_path, output_path)

    def pdf_to_base64_images(self, pdf_path: str) -> list[str]:
        """
        Convert a PDF to base64 encoded PNG images.

        Args:
            pdf_path (str): The path to the PDF file to convert.

        Returns:
            List[str]: A list of base64 encoded PNG images.
        """
        images = convert_from_path(pdf_path, use_pdftocairo=True, dpi=150, last_page=self.last_page)
        base64_images = []

        # Attempt to use a specific font, fallback to a default font if not available
        try:
            font = ImageFont.truetype("arial.ttf", 35)
        except OSError:
            font = ImageFont.load_default(35)

        for i, image in enumerate(images):
            draw = ImageDraw.Draw(image)
            page_number_text = f"Page number {i + 1} (Note this)"
            bbox = draw.textbbox((0, 0), page_number_text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((image.width - text_width) / 2, 10),
                page_number_text,
                fill="purple",
                font=font
            )
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            base64_images.append(img_str)
        
        return base64_images

    def format_solution(self, questions: Questions, solutions: list[Solution]) -> str:
        markdown_output = f"# {questions.assignment_topic}\n\n"  # Start with the assignment topic as the heading

        # Iterate over each question and its corresponding solution
        for question, solution in zip(questions.questions_or_tasks, solutions):
            # Add the question number and the actual question
            question_header = f"\n\n## {question.question_to_solve_markdown}\n\n"
            # Add the solution in markdown format
            solution_content = f"\n\nAns. \n{solution.solution_markdown}\n\n"
            # Append each formatted section to the main markdown output
            markdown_output += question_header + solution_content

        return markdown_output


if __name__ == "__main__":
    solver = AssignmentSolver(
        ChatOpenAI(model="gpt-4o", temperature=0),
        llm_solver=ChatOpenAI(model="gpt-4o", temperature=0).bind(response_format={"type": "json_object"}),
        solver_tools=[]
    )
    questions, images = solver.extract_questions("/home/zain/Documents/test.txt")
    print(questions)
    solutions = solver.solve_questions(questions, images, "")
    md_answer = solver.format_solution(questions, solutions)
    b = solver.markdown_to_docx(md_answer)
    with open("answer.docx", "wb") as fp:
        fp.write(b)
    
    with open("Answer.md", "w") as fp:
        fp.write(md_answer)
