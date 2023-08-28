from langchain import PromptTemplate
import firebase
import os
from shutil import copyfile
from pydantic import BaseModel, Field
from typing import Optional, List, Union
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
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        return not any(True for _ in docs)

    def create_template(
        self, template: TemplateModel, file_path: str
    ) -> Union[None, str]:
        if not self.is_template_name_unique(template.template_name):
            return "Template name already exists."
        template_dict = template.model_dump()
        _, doc_ref = self.template_collection.add(template_dict)
        doc_id = doc_ref.id
        file_extension = os.path.splitext(file_path)[1]
        self._notify_observers(template)
        self.upload_template_file(file_path, doc_id, file_extension)
        return None

    def read_template(self, template_name: str) -> Union[TemplateModel, None]:
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        for doc in docs:
            return TemplateModel(**doc.to_dict())
        return None

    def update_template(self, template_name: str, updated_data: dict) -> None:
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        for doc in docs:
            doc.reference.update(updated_data)

    def delete_template(self, template_name: str, file_extension: str) -> None:
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        for doc in docs:
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

    def get_template_file(
        self, template_name: str, file_extension: str
    ) -> Union[str, None]:
        docs = self.template_collection.where(
            "template_name", "==", template_name
        ).stream()
        doc_id = None
        for doc in docs:
            doc_id = doc.id
            break
        if doc_id is None:
            return None

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
    template_manager, knowledge_manager = initialize_managers(OPENAI_API_KEY)

    presentation_maker = PresentationMaker(
        template_manager, knowledge_manager, OPENAI_API_KEY
    )
    print(presentation_maker.get_best_template("OPerating systems").slides)
