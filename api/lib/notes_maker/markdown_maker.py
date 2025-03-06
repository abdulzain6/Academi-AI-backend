from enum import Enum
import re
import tempfile
import pypandoc
import os
import io
import requests
from langchain.pydantic_v1 import BaseModel, Field
from docx import Document
from docx.shared import RGBColor
from langchain.chat_models.base import BaseChatModel
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from concurrent.futures import ThreadPoolExecutor


class MarkdownData(BaseModel):
    content: str = Field(
        json_schema_extra={"description": "The notes content in markdown format"}
    )

class NoteCategory(Enum):
    GENERAL = "General"
    MATHS = "Maths"
    SCIENCE = "Science"
    HISTORY = "History"
    GEOGRAPHY = "Geography"
    LITERATURE = "Literature"
    PHILOSOPHY = "Philosophy"
    ECONOMICS = "Economics"
    BUSINESS = "Business"
    COMPUTER_SCIENCE = "Computer Science"
    ENGINEERING = "Engineering"
    MEDICINE = "Medicine"
    LAW = "Law"
    PSYCHOLOGY = "Psychology"
    SOCIOLOGY = "Sociology"
    ANTHROPOLOGY = "Anthropology"
    POLITICAL_SCIENCE = "Political Science"
    ENVIRONMENTAL_SCIENCE = "Environmental Science"
    PHYSICS = "Physics"
    CHEMISTRY = "Chemistry"
    BIOLOGY = "Biology"
    OTHER = "Other"


class Metadata(BaseModel):
    title: str
    is_content_general: bool
    reason_why_its_general: str
    is_meaningful: bool
    is_useful_for_students: bool
    category: NoteCategory


class Image(BaseModel):
    image_link: str
    image_title: str


class RelevantImages(BaseModel):
    images: list[Image]


class MarkdownNotesMaker:
    def __init__(self, llm: BaseChatModel, searxng_host: str):
        self.llm = llm
        self.searxng_host = searxng_host

    def make_notes_from_string_return_string_only(
        self, string: str, instructions: str, title: str
    ) -> str:
        try:
            images = self.search_images(title)
        except Exception as e:
            images = RelevantImages(images=[])

        if images.images:
            images_prompt = f"""Use the following images to make the notes as well:
    {images}
    ============
    IMPORTANT: When including images in your notes, you MUST use proper Markdown image syntax: ![image title](image_url)
    Make sure to place images at appropriate locations within your content to illustrate relevant concepts.
    This will prevent images from being too large or too small in the final document.
    Do not stuff images at one place only one at one place.
    ============"""
        else:
            images_prompt = ""

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
Only make notes in english no matter what the data language is
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Use the following data to make the notes:
{data}
============

{images_prompt}

Follow the instructions below also:
============
{instructions}
============

The notes in markdown (RETURN NO OTHER TEXT):"""
                ),
            ],
            input_variables=["data", "instructions", "images_prompt"],
        )
        notes = self.llm.invoke(
            prompt.format_messages(
                data=string, instructions=instructions, images_prompt=images_prompt
            )
        ).content

        # Extract content from markdown code blocks
        code_block_pattern = r"```(?:markdown)?\s*([\s\S]*?)\s*```"
        code_blocks = re.findall(code_block_pattern, notes, re.IGNORECASE)

        if code_blocks:
            # Join all extracted code blocks
            extracted_content = "\n\n".join(code_blocks)
            return extracted_content.strip()
        else:
            # If no code blocks found, return the original notes
            return notes.strip()

    def generate_title(self, content: str) -> Metadata:
        structured_llm = self.llm.with_structured_output(Metadata)
        return structured_llm.invoke(
            [
                SystemMessage(
                    content="""Your purpose is to generate one line title from the notes given to you. 
You will also check if the content is general.
If the content is seen by someone, they should be able to understand the content.
Remember we need to filter content for students, If the content discusses a topic that makes no sense without additional context it will not be meaningful.
One should be able to understand in one go.
Content will not be meaningful if its too short. It should cover the whole story
"""
                ),
                HumanMessage(
                    content=f"Genrate metadata for the following content: \n{content}"
                ),
            ]
        )

    def make_notes(self, data: MarkdownData, context: None = None):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            pypandoc.convert_text(
                data.content,
                "docx",
                format="md",
                outputfile=temp_file.name,
                sandbox=True,
            )
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

    def search_images(self, query: str, limit: int = 5) -> RelevantImages:
        params = {"q": query, "categories": "images", "format": "json", "pageno": 1}

        response = requests.get(f"{self.searxng_host}/search", params=params)
        if response.status_code != 200:
            return RelevantImages(images=[])

        results = response.json().get("results", [])
        print(f"Got results from searxng: {len(results)}")

        # Sort results by score in descending order
        sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)

        # Extract image URLs
        candidate_links = [
            img.get("img_src") for img in sorted_results if img.get("img_src")
        ][: limit * 2]

        # Function to validate individual image link
        def validate_image_link(img_src):
            try:
                # Verify the link is accessible with a HEAD request (less bandwidth)
                head_response = requests.head(img_src, timeout=3)
                if head_response.status_code == 200:
                    return img_src
                return None
            except requests.RequestException:
                # Skip images with invalid URLs or connection issues
                return None

        # Validate links in parallel using ThreadPoolExecutor
        valid_links = []
        with ThreadPoolExecutor(max_workers=min(10, len(candidate_links))) as executor:
            for result in executor.map(validate_image_link, candidate_links):
                if result:
                    valid_links.append(result)
                    if len(valid_links) >= limit:
                        break

        image_links = valid_links

        messages = [
            SystemMessage(
                content=f"""
You are an AI designed to look at images and only return images that are relevant to the query.
Only return relevant images with proper titles.
Only return super relevant images, if no image is relevant return nothing.
Limit your response to a maximum of {limit} images.
The image and description should show the full picture, this is for students. we need images to convey full info"""
            )
        ]
        for link in image_links:
            messages.extend(
                [
                    HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": f"Here is an image with link: {link}. Look at it carefully.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": link,
                                    "detail": "low",
                                },
                            },
                        ]
                    ),
                    AIMessage(
                        content="I have seen the image carefully and understood what it is."
                    ),
                ]
            )
        messages.append(
            HumanMessage(
                content=f"Here is the query: {query}. Return only the images that are relevant to the query"
            )
        )
        return self.llm.with_structured_output(RelevantImages).invoke(messages)


if __name__ == "__main__":
    from langchain_openai import AzureChatOpenAI

    notes_maker = MarkdownNotesMaker(
        llm=AzureChatOpenAI(
            **{
                "api_version": "2024-08-01-preview",
                "azure_deployment": "gpt-4o-mini",
            }
        ),
        searxng_host="http://localhost:8080",
    )
    print(
        notes_maker.make_notes_from_string_return_string_only("Operating systems", "")
    )
