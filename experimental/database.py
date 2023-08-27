import firebase
import os
from shutil import copyfile
from pydantic import BaseModel
from typing import Optional, List, Union
from firebase_admin import firestore, storage
from abc import ABC, abstractmethod
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain.docstore.in_memory import InMemoryDocstore
from langchain.schema import Document
from qdrant_client import QdrantClient


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
        return Qdrant(
            embeddings=OpenAIEmbeddings(
                openai_api_key=self.openai_api_key
            ),
            client=QdrantClient(),
            collection_name="templates"
        )
        
    def add_documents(self, documents: List[Document]) -> None: 
        self.vectorstore.add_documents(documents)
        
    def update(self, template: TemplateModel) -> None:
        document = Document(page_content=f"{template.template_description} {template.template_name}", metadata={"name" : template.template_name})
        self.add_documents([document])
        
    def get_best_template(self, topic: str) -> str:
        return self.vectorstore.similarity_search(topic, k=1)[0].page_content
        

if __name__ == "__main__":
    template_manager = TemplateDBManager()
    knowledge_manager = KnowledgeManager("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")
    templates = template_manager.get_all_templates()
    docs = [Document(page_content=f"{template.template_description} {template.template_name}", metadata={"name" : template.template_name}) for template in templates]
    knowledge_manager.add_documents(docs)
    template_manager.register_observer(knowledge_manager)
    
    
    print(knowledge_manager.get_best_template("Operating systems"))
    