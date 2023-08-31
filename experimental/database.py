import copy
import logging
import re
import shutil, six
from tempfile import NamedTemporaryFile
from langchain import PromptTemplate
import firebase
import os
from shutil import copyfile
from pydantic import BaseModel, Field
from pptx.enum.shapes import MSO_SHAPE_TYPE

from typing import Dict, Optional, List, Tuple, Union
from firebase_admin import firestore, storage
from abc import ABC, abstractmethod
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import Document
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from exceptions import NoValidSequenceException
from pptx.slide import Slide
from pptx import Presentation
from pptx.util import Pt
from pptx.enum.text import PP_ALIGN
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup



class PresentationInput(BaseModel):
    topic: str
    instructions: str
    number_of_pages: int
    negative_prompt: str


class PresentationSequencePart(BaseModel):
    page_number: int = Field(
        json_schema_extra={
            "description": "The page number of the slide. Make sure this isn't repeated"
        }
    )
    slide_detail: str = Field(
        json_schema_extra={"description": "What the slide should be about."}
    )
    slide_type: str = Field(json_schema_extra={"description": "The type of the slide."})


class PlaceholderData(BaseModel):
    placeholder_name: str = Field(
        json_schema_extra={
            "description": "The name of the placeholder. Make sure name is exactly same"
        }
    )
    placeholder_data: str = Field(
        json_schema_extra={"description": "The data to display in the placeholder. Make sure it fits in a presentaion slide must be short (Important) 50-80 words"}
    )


class Placeholders(BaseModel):
    placeholders: Optional[List[PlaceholderData]] = Field(
        json_schema_extra={"description": "The placeholder data"}
    )


class PresentationSequence(BaseModel):
    slide_sequence: List[PresentationSequencePart] = Field(
        json_schema_extra={
            "description": "The sequence of slides used to make the presentation"
        }
    )


class PlaceholderModel(BaseModel):
    name: str
    description: Optional[str]


class SlideModel(BaseModel):
    slide_type: str
    page_number: int
    placeholders: List[PlaceholderModel]


class TemplateModel(BaseModel):
    template_name: str
    template_description: str
    category: Optional[str]
    version: Optional[str]
    aspect_ratio: Optional[str]
    color_scheme: Optional[List[str]]
    slides: List[SlideModel]
    file_extension: str = ".pptx"



class TemplateObserver(ABC):
    @abstractmethod
    def update(self, template: TemplateModel) -> None:
        pass


class TemplateListManager(TemplateObserver):
    def __init__(self) -> None:
        self.templates: List[TemplateModel] = []

    def update(self, template: TemplateModel) -> None:
        self.templates.append(template)


class TemplateDBManager:
    def __init__(self, local_storage_path: str = "temp") -> None:
        self.db = firestore.client()
        self.template_collection = self.db.collection("templates")
        self.bucket = storage.bucket()
        self.local_storage_path = local_storage_path
        self._observers: List[TemplateObserver] = []
        if not os.path.exists(self.local_storage_path):
            os.makedirs(self.local_storage_path)

    def register_observer(self, observer: TemplateObserver) -> None:
        self._observers.append(observer)

    def _notify_observers(self, template: TemplateModel) -> None:
        for observer in self._observers:
            observer.update(template)

    def is_template_name_unique(self, template_name: str) -> bool:
        return self._find_template_by_name(template_name) is None
    
    def _find_template_by_name(self, template_name: str):
        """Helper function to find a template by its name."""
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        for doc in docs:
            return doc
        return None

    def create_template(self, template: TemplateModel, file_path: str) -> Union[None, str]:
        if not self.is_template_name_unique(template.template_name):
            return "Template name already exists."

        file_extension = os.path.splitext(file_path)[1]
        template.file_extension = file_extension

        template_dict = template.model_dump()
        _, doc_ref = self.template_collection.add(template_dict)

        doc_id = doc_ref.id
        self._notify_observers(template)
        
        self.upload_template_file(file_path, doc_id, file_extension)

        return None

    def read_template(self, template_name: str) -> Union[TemplateModel, None]:
        doc = self._find_template_by_name(template_name)
        return TemplateModel(**doc.to_dict()) if doc else None

    def update_template(self, template_name: str, updated_data: dict) -> None:
        if doc := self._find_template_by_name(template_name):
            doc.reference.update(updated_data)

    def delete_template(self, template_name: str) -> None:
        if doc := self._find_template_by_name(template_name):
            doc_data = doc.to_dict()
            file_extension = doc_data.get('file_extension', '')
            doc_id = doc.id
            doc.reference.delete()
            self.delete_template_file(doc_id, file_extension)

    def delete_template_file(self, doc_id: str, file_extension: str) -> None:
        blob = self.bucket.blob(f"templates/{doc_id}{file_extension}")
        blob.delete()
        local_path = os.path.join(self.local_storage_path, f"{doc_id}{file_extension}")
        if os.path.exists(local_path):
            os.remove(local_path)

    def get_all_templates(self) -> List[TemplateModel]:
        docs = self.template_collection.stream()
        return [TemplateModel(**doc.to_dict()) for doc in docs]

    def get_template_file(self, template_name: str) -> Union[str, None]:
        doc = self._find_template_by_name(template_name)  # Assuming _find_template_by_name returns the Firestore document
        if doc is None:
            return None

        doc_data = doc.to_dict()
        file_extension = doc_data.get('file_extension', '.pptx')  # Fetch the file extension from the document
        doc_id = doc.id

        filename = f"{doc_id}{file_extension}"
        local_path = os.path.join(self.local_storage_path, filename)

        if os.path.exists(local_path):
            return local_path

        cloud_path = f"templates/{filename}"
        blob = self.bucket.blob(cloud_path)
        blob.download_to_filename(local_path)

        return local_path

    def upload_template_file(
        self, file_path: str, doc_id: str, file_extension: str
    ) -> None:
        blob = self.bucket.blob(f"templates/{doc_id}{file_extension}")
        blob.upload_from_filename(file_path)
        local_path = os.path.join(self.local_storage_path, f"{doc_id}{file_extension}")
        copyfile(file_path, local_path)


class KnowledgeManager(TemplateObserver):
    def __init__(self, openai_api_key: str) -> None:
        self.openai_api_key = openai_api_key
        self.vectorstore = self.get_vectorstore()

    def get_vectorstore(self) -> Qdrant:
        client = QdrantClient(location=":memory:")
        embedding = OpenAIEmbeddings(openai_api_key=self.openai_api_key)
        partial_embeddings = embedding.embed_documents(["test"])
        vector_size = len(partial_embeddings[0])

        vectors_config = rest.VectorParams(
            size=vector_size,
            distance=rest.Distance.COSINE,
        )
        client.create_collection("templates", vectors_config=vectors_config)
        return Qdrant(embeddings=embedding, client=client, collection_name="templates")

    def add_documents(self, documents: List[Document]) -> None:
        self.vectorstore.add_documents(documents)

    def update(self, template: TemplateModel) -> None:
        document = Document(
            page_content=f"{template.template_description} {template.template_name}",
            metadata={"name": template.template_name},
        )
        self.add_documents([document])

    def get_best_template(self, topic: str) -> str:
        return self.vectorstore.similarity_search(topic, k=1)[0].metadata["name"]


class PresentationMaker:
    def __init__(
        self,
        template_manager: TemplateDBManager,
        knowledge_manager: KnowledgeManager,
        openai_api_key: str,
    ) -> None:
        self.template_manager = template_manager
        self.knowledge_manager = knowledge_manager
        self.openai_api_key = openai_api_key

    def get_best_template(self, topic: str) -> TemplateModel:
        template_name = self.knowledge_manager.get_best_template(topic)
        return self.template_manager.read_template(template_name)

    def format_placeholders(self, placeholders: List[PlaceholderModel]) -> str:
        formatted_str = "Placeholders:\n"
        if not placeholders:
            formatted_str += "No placeholders."
        for placeholder in placeholders:
            formatted_str += f"  - Name: {placeholder.name}\n"
            formatted_str += f"    Description: {placeholder.description}\n"
        return formatted_str

    def format_slides(self, slides: List[SlideModel]) -> str:
        formatted_str = "Slides Information:\n"
        formatted_str += "=" * 40 + "\n"
        for slide in slides:
            formatted_str += f"Slide Type: {slide.slide_type}\n"
            formatted_str += self.format_placeholders(slide.placeholders)
            formatted_str += "=" * 40 + "\n"
        return formatted_str

    def create_sequence(
        self, template: TemplateModel, presentation_input: PresentationInput
    ) -> PresentationSequence:
        prompt_template = """
You are an AI designed to assist in creating presentations. You are to pick a sequence of slides to create a presentation
on the topic "{topic}". THe presentation will be of {pages} pages. 
You must follow the following instructions:
{instructions}
==========================================
You must not do the following:
{negative_prompt}
==========================================

Here are the available slides with the placeholders in them for automatic presentation generation:
==========================================
{slides}
==========================================

Lets think step by step, Looking at the slide types and the placeholders inside them 
to create a sequence of slides that can be used to create a perfect presentation on {topic} of {pages} pages.
Do not choose slide types that are not shown to you.

{format_instructions}
        """

        parser = PydanticOutputParser(pydantic_object=PresentationSequence)
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=[
                "topic",
                "pages",
                "instructions",
                "negative_prompt",
                "slides",
            ],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )

        chain = LLMChain(
            prompt=prompt,
            output_parser=parser,
            llm=ChatOpenAI(openai_api_key=self.openai_api_key, temperature=0),
        )
        return chain.run(
            topic=presentation_input.topic,
            pages=presentation_input.number_of_pages,
            instructions=presentation_input.instructions,
            negative_prompt=presentation_input.negative_prompt,
            slides=self.format_slides(template.slides),
        )

    def validate_slides(
        self, template: TemplateModel, slides: PresentationSequence
    ) -> bool:
        slide_types = [slide.slide_type for slide in slides.slide_sequence]
        slides_to_choose_from = [slide.slide_type for slide in template.slides]
        return all(slide in slides_to_choose_from for slide in slide_types)

    def get_slide_content(
        self,
        sequence_part: PresentationSequencePart,
        slide: SlideModel,
        presentation_input: PresentationInput,
        all_slides: list[PresentationSequencePart]
    ) -> Placeholders:
        prompt_template = """
You are an AI designed to assist in automatic presentation generation.
You will generate content for a slide by looking at placeholders and return what should they be filled with.

=====================
The presentation is about {presentation_topic}
Here are all the slides for the presentation:
{slides}
=====================


The slide you will generate content for is {slide_detail}. This is page {page_no} of the ppt
Here are the placeholders we want to fill:
=====================
{placeholders}
=====================

Follow the following instructions:
==============
You must fill all placeholders.
If there are no placeholders return an empty list.
{instructions}
==============

Do not do the following:
==============
Do not choose slide types that are not shown to you.
{negative_prompt}
==============


Lets think step by step, Looking at the placeholders and their descriptions to fill them for the slide topic {slide_detail}. Follow all rules above! Ensure it fits in a slide
{format_instructions}
Make sure the placeholder content is small enough to fit a slide dont go over 70 words per placeholder,,,, lesser content is better than too much (Important).
Keep in mind points take up more space then paragraph so use 50 words for placeholders with points (Very important!!)
Follow the damn rules, you gave 150 words for a placeholder last time that caused error so keep it short. Be super brief!
Lets think step by step to accomplish this.
        """
        parser = PydanticOutputParser(pydantic_object=Placeholders)
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=[
                "placeholders",
                "slide_detail",
                "slides",
                "presentation_topic",
                "instructions",
                "negative_prompt",
                "page_no"
            ],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        chain = LLMChain(
            output_parser=parser,
            prompt=prompt,
            llm=ChatOpenAI(openai_api_key=self.openai_api_key, temperature=0, max_tokens=250 ,model="gpt-3.5-turbo"),
        )
        placeholders: Placeholders =  chain.run(
            placeholders=self.format_placeholders(slide.placeholders),
            slide_detail=sequence_part.slide_detail,
            slides="\n".join([slide.slide_detail for slide in all_slides]),
            presentation_topic=presentation_input.topic,
            instructions=presentation_input.instructions,
            negative_prompt=presentation_input.negative_prompt,
            page_no=sequence_part.page_number
        )
        for placeholder in placeholders.placeholders:
            placeholder.placeholder_data = placeholder.placeholder_data.replace("\n\n", "\n")
        
        return placeholders
        
    
    def remove_placeholders_and_artifacts(self, slide) -> None:
        """
        Removes empty placeholders and other artifacts from a slide.

        Args:
        slide (Slide): The slide to clean up.

        Returns:
        None
        """
        shapes_to_remove = [
            shape
            for shape in slide.shapes
            if shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER
            and (shape.has_text_frame and not shape.text)
        ]
        for shape in shapes_to_remove:
            sp = shape._element
            sp.getparent().remove(sp)
            
    def duplicate_slide_with_temp_img(self, prs: Presentation, slide_index: int, layout_index: int) -> None:
        print("Starting slide duplication...")
        slide_to_copy = prs.slides[slide_index]
        slide_layout = prs.slide_layouts[layout_index]
        
        print(f"Number of shapes in slide to copy: {len(slide_to_copy.shapes)}")
        
        new_slide = prs.slides.add_slide(slide_layout)
        
        print(f"Number of shapes in new slide: {len(new_slide.shapes)}")
        
        img_dict = {}
        
        for shape in slide_to_copy.shapes:
            try:
                print(f"Processing shape: {shape.name}")
                
                if 'Picture' in shape.name:
                    with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                        temp_file.write(shape.image.blob)
                    img_dict[temp_file.name] = (shape.left, shape.top, shape.width, shape.height)
                else:
                    el = shape.element
                    new_el = copy.deepcopy(el)
                    new_slide.shapes._spTree.insert_element_before(new_el, 'p:extLst')
                    
                    print(f"Shape element inserted: {new_el.tag}")
                    
            except Exception as e:
                print(f"Could not copy shape due to: {e}")

        for img_path, dims in img_dict.items():
            new_slide.shapes.add_picture(img_path, *dims)
            os.remove(img_path)

        self.remove_placeholders_and_artifacts(new_slide)
        print(f"Slide duplication completed. New slide has {len(new_slide.shapes)} shapes.")
        
    def create_presentation_from_sequence(self, sequence: PresentationSequence, template_path: str, template_slides: List[SlideModel]) -> Presentation:
        print("Creating a new presentation from sequence...")

        # Create the slide_type to layout_index mapping dynamically
        slide_type_to_layout_index = {slide.slide_type: slide.page_number - 1 for slide in template_slides}
        print(f"Map {slide_type_to_layout_index}")

        # Step 1: Load Template Presentation
        prs = Presentation(template_path)

        # Step 2: Iterate Through the Sequence
        for slide_part in sequence.slide_sequence:
            print(f"Processing slide type: {slide_part.slide_type}")

            if slide_model := next(
                (
                    slide
                    for slide in template_slides
                    if slide.slide_type == slide_part.slide_type
                ),
                None,
            ):
                index_to_duplicate = slide_model.page_number - 1
                print(f"Index to duplicate: {index_to_duplicate}")

                # Use the mapping to get the layout index
                layout_index = slide_type_to_layout_index.get(slide_part.slide_type, 0)
                print(f"Layout index: {layout_index}")

                # Debugging: Slide Count Before Duplication
                print(f"Slide Count Before Duplication: {len(prs.slides)}")

                self.duplicate_slide_with_temp_img(prs, index_to_duplicate, layout_index)

                # Debugging: Slide Count After Duplication
                print(f"Slide Count After Duplication: {len(prs.slides)}")

        # Step 3: Delete All Original Slides
        for i in range(len(prs.slides) - len(sequence.slide_sequence) - 1, -1, -1):
            rId = prs.slides._sldIdLst[i].rId
            prs.part.drop_rel(rId)
            del prs.slides._sldIdLst[i]

        return prs

    def fill_presentation_with_content(self, prs: Presentation, sequence: PresentationSequence, presentation_input: PresentationInput, template_slides: List[SlideModel]) -> None:
        print("Filling in placeholders...")
        for i, slide_part in enumerate(sequence.slide_sequence):
            print(f"Filling in placeholders for slide: {i + 1}")
            template_slide = self.get_slide_by_type(slide_part.slide_type, template_slides)
            slide_content = self.get_slide_content(slide_part, template_slide, presentation_input, sequence.slide_sequence)
            presentation_slide = prs.slides[i]
            self.replace_placeholders_in_single_slide(presentation_slide, slide_content)

    def make_presentation(self, presentation_input: PresentationInput) -> None:
        print("Fetching best template...")
        template = self.get_best_template(presentation_input.topic)
        slide_path = self.template_manager.get_template_file(template.template_name)

        print("Creating and validating slide sequence...")
        for _ in range(3):
            sequence = self.create_sequence(template, presentation_input)
            if self.validate_slides(template, sequence):
                break
        else:
            raise NoValidSequenceException("Couldn't find the best sequence")

        print("Sorting the slide sequence...")
        sequence.slide_sequence = sorted(sequence.slide_sequence, key=lambda x: x.page_number if x else 0)

        prs = self.create_presentation_from_sequence(sequence, slide_path, template.slides)
        
        new_slide_path = "example_modified.pptx"

        self.fill_presentation_with_content(prs, sequence, presentation_input, template.slides)

        print("Saving the new presentation...")
        prs.save(new_slide_path)
        print("Presentation saved successfully.")

    def replace_placeholders_in_single_slide(self, slide: Slide, placeholders: Placeholders):
        for shape in slide.shapes:
            if shape.has_text_frame:
                text_frame = shape.text_frame                
                for paragraph in text_frame.paragraphs:
                    for run in paragraph.runs:
                        for placeholder in placeholders.placeholders:
                            if placeholder.placeholder_name in run.text:
                                run.text = run.text.replace("{{" + placeholder.placeholder_name+ "}}", placeholder.placeholder_data)       
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for placeholder in placeholders.placeholders:
                            if placeholder.placeholder_name in cell.text:
                                cell.text = cell.text.replace("{{" + placeholder.placeholder_name + "}}", placeholder.placeholder_data)
        return slide

    def get_slide_by_type(self, type: str, slides: list[SlideModel]) -> SlideModel:
        for slide in slides:
            if slide.slide_type.lower() == type.lower():
                return slide


def initialize_managers(
    openai_api_key: str, local_storage_path: str = "temp"
) -> tuple[TemplateDBManager, KnowledgeManager]:
    template_manager = TemplateDBManager(local_storage_path)
    knowledge_manager = KnowledgeManager(openai_api_key)
    templates = template_manager.get_all_templates()
    docs = [
        Document(
            page_content=f"{template.template_description} {template.template_name}",
            metadata={"name": template.template_name},
        )
        for template in templates
    ]
    knowledge_manager.add_documents(docs)
    template_manager.register_observer(knowledge_manager)
    return template_manager, knowledge_manager


if __name__ == "__main__":
    OPENAI_API_KEY = "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"
    import langchain

    langchain.verbose = False
    template_manager, knowledge_manager = initialize_managers(OPENAI_API_KEY)

    presentation_maker = PresentationMaker(
        template_manager, knowledge_manager, OPENAI_API_KEY
    )
    print(
        presentation_maker.make_presentation(
            PresentationInput(
                topic="Operaring systems",
                instructions="Explain as if i was 10",
                number_of_pages=3,
                negative_prompt="Dont use hard vocabulary",
            )
        )
    )
