import json
import re
from pptx.util import Inches
import os
from pydantic import BaseModel, ValidationError
from typing import Optional, List, Union
from gridfs import GridFS
from abc import ABC, abstractmethod
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from pptx import Presentation
from pymongo import MongoClient
from pymongo.collection import Collection
from typing import List, Union, Dict, Optional



class PlaceholderModel(BaseModel):
    name: str
    description: Optional[str] = None
    is_image: bool = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None


class SlideModel(BaseModel):
    slide_type: str
    page_number: int
    placeholders: List[PlaceholderModel]


class TemplateModel(BaseModel):
    template_name: str
    template_description: str
    category: Optional[str] = None
    version: Optional[str] = None
    aspect_ratio: Optional[str] = None
    color_scheme: Optional[List[str]] = None
    slides: List[SlideModel]
    file_extension: str = "pptx"
    word_limit_para: int = 93
    word_limit_points: int = 80
    word_limit_hybrid: int = 75
    file_name: Optional[str] = None 


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
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        local_storage_path: str = "temp",
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.template_collection: Collection = self.db["templates"]
        self.fs = GridFS(self.db, collection="template_files")
        self.template_collection.create_index("template_name", unique=True)

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

    def _find_template_by_name(self, template_name: str) -> Optional[Dict]:
        query = {"template_name": {"$regex": re.compile(f'^{re.escape(template_name)}$', re.IGNORECASE)}}
        return self.template_collection.find_one(query)

    def create_template(
        self, template: TemplateModel, file_path: str
    ) -> Union[None, str]:
        if not self.is_template_name_unique(template.template_name):
            return "Template name already exists."

        file_extension = os.path.splitext(file_path)[1]
        template.file_extension = file_extension

        with open(file_path, "rb") as f:
            file_id = self.fs.put(f.read(), filename=template.template_name)

        template_dict = template.model_dump()
        template_dict["file_id"] = file_id
        self.template_collection.insert_one(template_dict)

        self._notify_observers(template)
        return None

    def read_template(self, template_name: str) -> Union[TemplateModel, None]:
        doc = self._find_template_by_name(template_name)
        return TemplateModel(**doc) if doc else None

    def update_template(self, template_name: str, updated_data: Dict) -> None:
        self.template_collection.update_one(
            {"template_name": template_name}, {"$set": updated_data}
        )

    def delete_template(self, template_name: str) -> None:
        if doc := self._find_template_by_name(template_name):
            self.fs.delete(doc["file_id"])
            self.template_collection.delete_one({"_id": doc["_id"]})

    def get_all_templates(self) -> List[TemplateModel]:
        cursor = self.template_collection.find()
        return [TemplateModel(**doc) for doc in cursor]

    def get_template_file(self, template_name: str) -> Union[str, None]:
        doc = self._find_template_by_name(template_name)
        if doc is None:
            return None

        file_id = doc.get("file_id")
        if file_id is None:
            return None

        file_extension = doc.get("file_extension", "")
        local_path = os.path.join(self.local_storage_path, f"{file_id}{file_extension}")

        if not os.path.exists(local_path):
            with open(local_path, "wb") as f:
                f.write(self.fs.get(file_id).read())

        return local_path


class TemplateKnowledgeManager(TemplateObserver):
    def __init__(self) -> None:
        self.vectorstore = self.get_vectorstore()

    def get_vectorstore(self) -> Qdrant:
        client = QdrantClient(location=":memory:")
        embedding = OpenAIEmbeddings()
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


def initialize_managers(
    connection_string: str, database_name: str, local_storage_path: str = "temp"
) -> tuple[TemplateDBManager, TemplateKnowledgeManager]:
    template_manager = TemplateDBManager(connection_string, database_name, local_storage_path)
    knowledge_manager = TemplateKnowledgeManager()
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


class PresentationTemplateWizard:
    def __init__(self, ppt_file_path: str):
        self.ppt = Presentation(ppt_file_path)

    def get_image_dimensions(
        self, slide_number: int, placeholder_name: str
    ) -> Union[None, tuple]:
        slide = self.ppt.slides[slide_number - 1]  # Adjust for 1-based indexing

        for shape in slide.shapes:
            if shape.name == placeholder_name and shape.shape_type == 13:
                width_px = int(shape.width / Inches(1) * 96)  # Conversion to pixels
                height_px = int(shape.height / Inches(1) * 96)  # Conversion to pixels
                return width_px, height_px

        return None  # Return None if placeholder not found

    def wizard_cli(self) -> TemplateModel:
        print("Welcome to the Presentation Template Wizard!")

        template_name = input("Enter the template name: ")
        file_name = input("Enter filename ")
        template_description = input("Enter a description for the template: ")
        category = input("Enter the category (optional, press Enter to skip): ") or None
        version = input("Enter the version (optional, press Enter to skip): ") or None
        aspect_ratio = (
            input("Enter the aspect ratio (optional, press Enter to skip): ") or None
        )
        color_scheme = (
            input(
                "Enter color scheme as comma-separated values (optional, press Enter to skip): "
            ).split(",")
            if input("Do you have a color scheme? (y/n): ").lower() == "y"
            else None
        )
        word_limit_para = int(input("Enter the word limit for paragraphs: "))
        word_limit_points = int(input("Enter the word limit for points: "))

        slides = []

        while input("Do you want to add a slide? (y/n): ").lower() == "y":
            slide_type = input("Enter the slide type: ")
            page_number = int(input("Enter the page number: "))
            placeholders = []

            while input("Do you want to add a placeholder? (y/n): ").lower() == "y":
                name = input("Enter the name of the placeholder: ")
                is_image = input("Is this an image placeholder? (y/n): ").lower() == "y"

                description = (
                    "Write a Google search query for this image that is relevant to the topic."
                    if is_image
                    else input("Enter a description (optional, press Enter to skip): ")
                    or None
                )

                if is_image:
                    if dimensions := self.get_image_dimensions(page_number, name):
                        image_width, image_height = dimensions
                    else:
                        print(
                            "Couldn't find the placeholder in the slide, skipping image dimensions."
                        )
                        image_width, image_height = None, None
                else:
                    image_width, image_height = None, None

                placeholders.append(
                    PlaceholderModel(
                        name=name,
                        description=description,
                        is_image=is_image,
                        image_width=image_width,
                        image_height=image_height,
                    )
                )

            slides.append(
                SlideModel(
                    slide_type=slide_type,
                    page_number=page_number,
                    placeholders=placeholders,
                )
            )

        return TemplateModel(
            template_name=template_name,
            template_description=template_description,
            category=category,
            version=version,
            aspect_ratio=aspect_ratio,
            color_scheme=color_scheme,
            slides=slides,
            word_limit_para=word_limit_para,
            word_limit_points=word_limit_points,
            file_name=file_name
        )

def load_and_validate_templates(file_path: str) -> Union[List[TemplateModel], TemplateModel, None]:
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            templates = [TemplateModel(**item) for item in data]
            return templates
        elif isinstance(data, dict):
            template = TemplateModel(**data)
            return template
        else:
            print("Invalid JSON structure.")
            return None
    
    except ValidationError as e:
        print(f"Validation Error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    def load():
        manager = TemplateDBManager(os.getenv("MONGODB_URL"), "study-app")   
        loaded_templates = load_and_validate_templates("templates.json")
        for template in loaded_templates:
            manager.create_template(template, "template_dir/" + template.file_name)
    def input_and_save(file_path):
      #  manager = TemplateDBManager(os.getenv("MONGODB_URL"), "study-app")   
        loaded_templates = load_and_validate_templates("templates.json")
        model = PresentationTemplateWizard(file_path).wizard_cli()
        templates = loaded_templates.append(model)    
        updated_templates_json_str = json.dumps([template.dict() for template in templates], indent=4)
        updated_json_file_path = 'templatesupdated.json'
        with open(updated_json_file_path, 'w') as f:
            f.write(updated_templates_json_str)
    load()       
    #input_and_save("/home/zain/Akalmand.ai/api/lib/presentation_maker/template_dir/Azure_Versatility.pptx")