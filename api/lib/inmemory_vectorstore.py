from typing import List
from langchain.vectorstores.qdrant import Qdrant
from langchain.schema import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from langchain.embeddings.openai import OpenAIEmbeddings
from ..lib.embeddings import TogetherEmbeddingsParallel

class InMemoryVectorStore:
    def __init__(self, embeddings = None) -> None:
        if not embeddings:
            self.embeddings = TogetherEmbeddingsParallel(
               max_retries=2,
               timeout=5
            )
        else:
            self.embeddings = embeddings
        try:
            self.vectorstore = self.get_vectorstore()
        except Exception:
            self.embeddings = OpenAIEmbeddings()
            self.vectorstore = self.get_vectorstore()
        
        self.stored_page_docs = set()

    def get_vectorstore(self) -> Qdrant:
        client = QdrantClient(location=":memory:")
        embedding = self.embeddings
        partial_embeddings = embedding.embed_documents(["test"])
        vector_size = len(partial_embeddings[0])

        vectors_config = rest.VectorParams(
            size=vector_size,
            distance=rest.Distance.COSINE,
        )
        client.create_collection("vecs", vectors_config=vectors_config)
        return Qdrant(embeddings=embedding, client=client, collection_name="vecs")

    def add_documents(self, documents: List[Document], add_all: bool = False) -> None:
        if not add_all:
            new_documents = [doc for doc in documents if doc.page_content not in self.stored_page_docs]
            self.stored_page_docs.update([doc.page_content for doc in new_documents])
            if new_documents:
                self.vectorstore.add_documents(new_documents)
        else:
            self.vectorstore.add_documents(documents)


    def query_vectorstore(self, query: str, k: int = 3) -> list[Document]:
        return self.vectorstore.similarity_search(query, k=k)