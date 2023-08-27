from langchain.embeddings.base import Embeddings
from langchain.vectorstores import PGVector
from langchain.chat_models.base import BaseChatModel
from langchain.document_loaders import UnstructuredAPIFileLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores.pgvector import PGVector
from langchain.vectorstores._pgvector_data_models import EmbeddingStore
from langchain.document_loaders import WebBaseLoader, YoutubeLoader
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import Document, LLMResult
from langchain.chains import LLMChain
from langchain.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    StringPromptTemplate,
    HumanMessagePromptTemplate,
)

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Type, Dict, List, Tuple, Union
import logging, time


def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class CustomCallback(BaseCallbackHandler):
    def __init__(self, callback) -> None:
        self.callback = callback
        super().__init__()
        self.cached = True

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.cached = False
        if not self.cached:
            self.callback(token)

    def on_llm_end(self, response: LLMResult, *args, **kwargs) -> None:
        if self.cached:
            for chunk in split_into_chunks(response.generations[0][0].text, 8):
                self.callback(chunk)
                time.sleep(0.1)
        self.callback(None)


class PGVectorModified(PGVector):
    def delete(self, ids: List[str]) -> None:
        with Session(self._conn) as session:
            collection = self.get_collection(session)
            if not collection:
                raise ValueError("Collection not found")
            collection_uuid = collection.uuid
            session.query(EmbeddingStore).filter(
                and_(
                    EmbeddingStore.custom_id.in_(ids),
                    EmbeddingStore.collection_id == collection_uuid,
                )
            ).delete(synchronize_session="fetch")
            session.commit()


class KnowledgeManager:
    def __init__(
        self,
        embeddings: Embeddings,
        unstructured_api_key: str,
        connection_string: str,
        chunk_size: int = 1000,
    ) -> None:
        self.embeddings = embeddings
        self.unstructured_api_key = unstructured_api_key
        self.chunk_size = chunk_size
        self.connection_string = connection_string

    def split_docs(self, docs: Document) -> List[Document]:
        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size
        ).split_documents(docs)

    def load_data(self, file_path: str) -> Tuple[str, List[Document], bytes]:
        print(f"Loading {file_path}")
        loader = UnstructuredAPIFileLoader(
            file_path=file_path,
            api_key=self.unstructured_api_key,
        )

        docs = loader.load()
        print(f"Documents loaded {docs}")
        docs = self.split_docs(docs)
        contents = "\n\n".join([doc.page_content for doc in docs])

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        return contents, docs, file_bytes

    def injest_data(
        self,
        collection_name: str,
        documents: List[Document],
        ids: List[str] = None,
    ) -> List[str]:
        vectorstore = PGVector(self.connection_string, self.embeddings, collection_name)
        return vectorstore.add_documents(documents, ids=ids)

    def add_metadata_to_docs(self, metadata: Dict, docs: List[Document]):
        for document in docs:
            document.metadata.update(metadata)
        return docs

    def load_and_injest_file(
        self, collection_name: str, filepath: str, metadata: Dict
    ) -> Tuple[str, List[str], bytes]:
        contents, docs, file_bytes = self.load_data(filepath)
        docs = self.add_metadata_to_docs(metadata=metadata, docs=docs)
        ids = self.injest_data(collection_name=collection_name, documents=docs)
        return contents, ids, file_bytes

    def load_web_youtube_link(
        self,
        collection_name: str,
        metadata: Dict,
        youtube_link: str = None,
        web_url: str = None,
    ):
        if not youtube_link and not web_url:
            raise ValueError("Either weburl or youtube_link must be specified")

        if youtube_link and web_url:
            raise ValueError(
                "Either weburl or youtube_link must be specified. Not both."
            )

        if web_url:
            loader = WebBaseLoader(web_url)
        else:
            loader = YoutubeLoader.from_youtube_url(youtube_link)

        docs = loader.load()

        docs = self.split_docs(docs)
        contents = "\n\n".join([doc.page_content for doc in docs])
        docs = self.add_metadata_to_docs(metadata=metadata, docs=docs)
        ids = self.injest_data(collection_name=collection_name, documents=docs)
        return contents, ids, bytes(contents, encoding="utf-8")

    def delete_collection(self, collection_name: str) -> bool:
        try:
            vectorstore = PGVector(
                self.connection_string, self.embeddings, collection_name
            )
            vectorstore.delete_collection()
            return True
        except Exception:
            return False

    def delete_ids(self, collection_name: str, ids: list[str]):
        vectorstore = PGVectorModified(
            self.connection_string, self.embeddings, collection_name
        )
        return vectorstore.delete(ids)

    def query_data(
        self, query: str, collection_name: str, k: int, metadata: Dict[str, str] = None
    ):
        vectorstore = PGVector(self.connection_string, self.embeddings, collection_name)
        return vectorstore.similarity_search(query, k, filter=metadata)


class ChatManager:
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
"""
You are {ai_name}, an AI designed to provide information. 
You are to take the tone of a teacher.
Talk as if you're a teacher. Use the data provided to answer user questions. 
Only return the next message content in {language}. dont return anything else not even the name of AI.
You must answer the human in {language} (important)"""
            ),
            HumanMessagePromptTemplate.from_template(
                """
                
Help Data:
=========
{help_data}
=========

Let's think in a step by step, answer the humans question in {language}.

{conversation}

Human: {question}

{ai_name} ({language}):"""
            ),
        ],
        input_variables=[
            "ai_name",
            "help_data",
            "conversation",
            "question",
            "language",
        ],
    )

    def __init__(
        self,
        embeddings: Embeddings,
        llm_cls: Type[BaseChatModel],
        llm_kwargs: Dict[str, str],
        connection_string: str,
        conversation_limit: int,
        docs_limit: int,
        ai_name: str = "AI",
    ) -> None:
        self.embeddings = embeddings
        self.llm_cls = llm_cls
        self.llm_kwargs = llm_kwargs
        self.connection_string = connection_string
        self.conversation_limit = conversation_limit
        self.docs_limit = docs_limit
        self.ai_name = ai_name

    def query_data(
        self, query: str, collection_name: str, k: int, metadata: Dict[str, str] = None
    ):
        vectorstore = PGVector(self.connection_string, self.embeddings, collection_name)
        return vectorstore.similarity_search(query, k, filter=metadata)

    def chat(
        self,
        collection_name: str,
        prompt: str,
        chat_history: list[tuple[str, str]],
        language: str,
        stream: bool = True,
        callback_func: callable = None,
        k: int = 5,
        metadata: dict[str, str] = None,
        filename: str = None,
        model_name: str = "gpt-3.5-turbo",
    ) -> str:
        if metadata is None:
            metadata = {}

        llm = self.get_llm(stream=stream, callback_func=callback_func, model=model_name)
        conversation = self.format_messages(
            chat_history=chat_history,
            tokens_limit=self.conversation_limit,
            ai_name=self.ai_name,
            llm=llm
        )
        combined = (
            self.format_messages(
                chat_history=chat_history,
                tokens_limit=self.conversation_limit,
                human_only=True,
                llm=llm,
                ai_name=self.ai_name
            )
            + "\n"
            + f"Human: {prompt}"
        )
        if filename:
            metadata["file"] = filename

        similar_docs = self.query_data(
            combined, collection_name, metadata=metadata, k=k
        )
        similar_docs = self._reduce_tokens_below_limit(
            similar_docs, llm=llm, docs_limit=self.docs_limit
        )
        similar_docs_string = "\n".join([doc.page_content for doc in similar_docs])

        chain = LLMChain(llm=llm, prompt=self.prompt)
        return chain.run(
            ai_name=self.ai_name,
            help_data=similar_docs_string,
            conversation=conversation,
            question=prompt,
            language=language,
        )

    def format_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
        human_only: bool = False,
        ai_name: str = "AI",
    ) -> str:
        cleaned_msgs: List[Union[str, Tuple[str, str]]] = []
        tokens_used: int = 0

        for human_msg, ai_msg in chat_history:
            human_msg_formatted = f"Human: {human_msg}"
            ai_msg_formatted = f"{ai_name}: {ai_msg}"

            human_tokens = llm.get_num_tokens(human_msg_formatted)
            ai_tokens = llm.get_num_tokens(ai_msg_formatted)

            if not human_only:
                new_tokens_used = tokens_used + human_tokens + ai_tokens
            else:
                new_tokens_used = tokens_used + human_tokens

            if new_tokens_used > tokens_limit:
                break

            if human_only:
                cleaned_msgs.append(human_msg_formatted)
            else:
                cleaned_msgs.append((human_msg_formatted, ai_msg_formatted))

            tokens_used = new_tokens_used

        if human_only:
            return "\n\n".join(cleaned_msgs)
        else:
            return "\n\n".join(
                [f"{clean_msg[0]}\n\n{clean_msg[1]}" for clean_msg in cleaned_msgs]
            )

    def _reduce_tokens_below_limit(
        self, docs: list, docs_limit: int, llm: BaseChatModel
    ) -> list[Document]:
        num_docs = len(docs)
        tokens = [llm.get_num_tokens(doc.page_content) for doc in docs]
        token_count = sum(tokens[:num_docs])
        while token_count > docs_limit:
            num_docs -= 1
            token_count -= tokens[num_docs]

        return docs[:num_docs]

    def get_llm(self, stream=False, callback_func=None, model: str = "gpt-3.5-turbo"):
        if not stream:
            return self.llm_cls(
                model=model,
                **self.llm_kwargs,
                streaming=False,
            )

        return self.llm_cls(
            model=model,
            **self.llm_kwargs,
            streaming=True,
            callbacks=[CustomCallback(callback_func)],
        )


if __name__ == "__main__":
    from langchain.embeddings import OpenAIEmbeddings
    from langchain.chat_models import ChatOpenAI

    manager = KnowledgeManager(
        OpenAIEmbeddings(
            openai_api_key="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"
        ),
        ChatOpenAI,
        {"openai_api_key": "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"},
        "Is7uRcLSA8JmHEZGgBldmz2uU54Loo",
        "postgresql://postgres:8GP4h656&u#X@db.jxwuioejtfbvilnmkumc.supabase.co:6543/postgres",
    )

    print(
        manager.load_and_injest_file(
            "python", "../requirements.txt", {"file": "requirements.txt"}
        )
    )
    print(
        manager.load_and_injest_file(
            "python", "../requirements.txt", {"file": "requirements2.txt"}
        )
    )

    # print(manager.delete_ids("python", ["85f5079c-2968-11ee-bd4a-7920d26a8218"]))
    print(
        manager.query_data(
            "databases", "python", 1, metadata={"file": "requirements2.txt"}
        )
    )
