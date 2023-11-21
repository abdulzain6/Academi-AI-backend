import ipaddress
import logging
import random
import re
import socket
from urllib.parse import urlparse
from uuid import UUID
from langchain.embeddings.base import Embeddings
from langchain.chat_models.base import BaseChatModel
from langchain.document_loaders import UnstructuredAPIFileLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Qdrant
from langchain.document_loaders import WebBaseLoader, YoutubeLoader
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import Document, LLMResult
from langchain.chains import LLMChain
from langchain.embeddings import OpenAIEmbeddings, FakeEmbeddings
from langchain.agents.openai_functions_agent.base import OpenAIFunctionsAgent
from langchain.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    StringPromptTemplate,
    HumanMessagePromptTemplate,
)

from typing import Type, Dict, List, Tuple, Union
from qdrant_client import QdrantClient
import time

from langchain.agents import Tool
from langchain.agents import AgentExecutor
from pydantic import BaseModel, Field
from langchain.schema import (
    SystemMessage,
    BaseMessage,
    HumanMessage,
    AIMessage,
    LLMResult,
)
from api.lib.maths_solver.modified_openai_agent import ModifiedOpenAIAgent
from api.lib.maths_solver.python_exec_client import PythonClient
from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models.base import BaseChatModel
from langchain.chains import create_extraction_chain
from typing import Any, Optional, Sequence
from langchain.agents.agent import AgentExecutor
from langchain.callbacks.base import BaseCallbackManager
from langchain.schema.language_model import BaseLanguageModel
from langchain.tools.base import BaseTool
from langchain.schema.agent import AgentFinish


def split_into_chunks(text, chunk_size):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


class CustomCallback(BaseCallbackHandler):
    def __init__(self, callback, on_end_callback) -> None:
        self.callback = callback
        self.on_end_callback = on_end_callback
        super().__init__()
        self.cached = True

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self.cached = False
        if not self.cached:
            self.callback(token)

    def on_llm_end(self, response: LLMResult, *args, **kwargs) -> None:
        if self.cached:
            for chunk in split_into_chunks(response.generations[0][0].text, 8):
                self.callback(chunk)
                time.sleep(0.05)
        self.callback(None)
        self.on_end_callback(response.generations[0][0].text)


class CustomCallbackAgent(BaseCallbackHandler):
    def __init__(self, callback, on_end_callback) -> None:
        self.callback = callback
        self.on_end_callback = on_end_callback
        super().__init__()
        self.cached = True

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            self.cached = False
        if not self.cached:
            self.callback(token)

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self.callback(
            "\n*AI is using a tool/reading your files to better assist you...*\n"
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        self.callback("\n*AI has finished using the tool and will respond shortly...*\n\n")

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        try:
            self.on_end_callback(finish.return_values.get("output", ""))
            if self.cached:
                self.callback(finish.return_values.get("output", ""))
        except Exception:
            pass
        self.callback(None)


class QdrantModified(Qdrant):
    @staticmethod
    def create_collection_and_injest(
        collection_name: str,
        docs: list[Document],
        embeddings: OpenAIEmbeddings,
        **kwargs,
    ) -> list[str]:
        texts = [d.page_content for d in docs]
        metadatas = [d.metadata for d in docs]
        qdrant = Qdrant.construct_instance(
            texts=texts, embedding=embeddings, collection_name=collection_name, **kwargs
        )
        return qdrant.add_texts(texts, metadatas)


class KnowledgeManager:
    def __init__(
        self,
        embeddings: Embeddings,
        unstructured_api_key: str,
        unstructured_url: str,
        qdrant_api_key: str,
        qdrant_url: str,
        chunk_size: int = 1000,
    ) -> None:
        self.embeddings = embeddings
        self.unstructured_api_key = unstructured_api_key
        self.chunk_size = chunk_size
        self.qdrant_api_key = qdrant_api_key
        self.qdrant_url = qdrant_url
        self.unstructured_url = unstructured_url
        self.client = QdrantClient(
            url=self.qdrant_url, api_key=self.qdrant_api_key, prefer_grpc=True
        )

    def split_docs(self, docs: Document) -> List[Document]:
        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size
        ).split_documents(docs)

    def load_data(self, file_path: str) -> Tuple[str, List[Document], bytes]:
        print(f"Loading {file_path}")
        loader = UnstructuredAPIFileLoader(
            file_path=file_path,
            api_key=self.unstructured_api_key,
            url=self.unstructured_url,
        )

        docs = loader.load()
        print(f"Documents loaded {docs}")
        docs = self.split_docs(docs)
        contents = "\n\n".join([doc.page_content for doc in docs])

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        return contents, docs, file_bytes

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return bool(self.client.get_collection(collection_name))
        except Exception:
            return False

    def injest_data(
        self,
        collection_name: str,
        documents: List[Document],
        ids: List[str] = None,
    ) -> List[str]:
        vectorstore = Qdrant(self.client, collection_name, self.embeddings)
        if self.collection_exists(collection_name):
            return vectorstore.add_documents(documents)
        else:
            return QdrantModified.create_collection_and_injest(
                collection_name,
                documents,
                self.embeddings,
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                prefer_grpc=True,
            )

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

    def is_local_ip(self, ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    def validate_url(self, url: str) -> bool:
        allowed_schemes = ["http", "https"]

        parsed_url = urlparse(url)

        if parsed_url.scheme not in allowed_schemes:
            print("Invalid URL scheme")
            return False

        try:
            ip = socket.gethostbyname(parsed_url.hostname)
            if self.is_local_ip(ip):
                print("Local IPs are not allowed")
                return False
        except (socket.gaierror, TypeError):
            print("Invalid domain")
            return False

        return True

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
            if not self.validate_url(web_url):
                raise ValueError("Invalid URL")

            loader = WebBaseLoader(web_url)
        else:
            loader = YoutubeLoader.from_youtube_url(youtube_link)

        docs = loader.load()

        docs = self.split_docs(docs)
        contents = "\n\n".join([doc.page_content for doc in docs])

        if not contents:
            raise ValueError("Link has no data.")

        docs = self.add_metadata_to_docs(metadata=metadata, docs=docs)
        ids = self.injest_data(collection_name=collection_name, documents=docs)
        return contents, ids, bytes(contents, encoding="utf-8")

    def delete_collection(self, collection_name: str) -> bool:
        try:
            self.client.delete_collection(collection_name)
            return True
        except Exception:
            return False

    def delete_ids(self, collection_name: str, ids: list[str]):
        vectorstore = Qdrant(self.client, collection_name, self.embeddings)
        if ids:
            return vectorstore.delete(ids)

    def query_data(
        self, query: str, collection_name: str, k: int, metadata: Dict[str, str] = None
    ):
        try:
            vectorstore = Qdrant(self.client, collection_name, self.embeddings)
            return vectorstore.similarity_search(query, k, filter=metadata)
        except Exception:
            try:
                vectorstore = Qdrant(self.client, collection_name, FakeEmbeddings(size=1536))
                return vectorstore.similarity_search(query, k, filter=metadata)
            except Exception:
                return []


class ChatManagerRetrieval:
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """
You are {ai_name}, an AI teacher designed to teach students. You are {model_name} 
You are to take the tone of a teacher.
Talk as if you're a teacher. Use the data provided to answer user questions. 
Only return the next message content in {language}. dont return anything else not even the name of AI.
You must answer the human in {language} (important)
The help data is from files/subjects the human has provided and can be from webpages, youtube links, files, images and much more"""
            ),
            HumanMessagePromptTemplate.from_template(
                """
Help Data (This data is from files/subjects the human has provided and can be from webpages, youtube links, files, images and much more):
=========
{help_data}
=========

Let's think in a step by step, answer the humans question in {language}. Use the data provided by the human and personal knowledge to answer (Important)

{conversation}

Human: {question}

Use the help data to answer the student question

{ai_name} ({language}):"""
            ),
        ],
        input_variables=[
            "ai_name",
            "help_data",
            "conversation",
            "question",
            "language",
            "model_name",
        ],
    )

    def __init__(
        self,
        embeddings: Embeddings,
        qdrant_api_key: str,
        qdrant_url: str,
        conversation_limit: int,
        docs_limit: int,
        python_client: PythonClient,
        ai_name: str = "AcademiAI",
        base_tools: list[Tool] = [],
    ) -> None:
        self.embeddings = embeddings
        self.qdrant_api_key = qdrant_api_key
        self.qdrant_url = qdrant_url
        self.conversation_limit = conversation_limit
        self.docs_limit = docs_limit
        self.ai_name = ai_name
        self.python_client = python_client
        self.base_tools = base_tools
        self.client = QdrantClient(
            url=self.qdrant_url, api_key=self.qdrant_api_key, prefer_grpc=True
        )

    def make_code_runner(self) -> list[Tool]:
        try:
            libraries = self.python_client.get_available_libraries()["libraries"]
        except Exception:
            libraries = []

        description = f"""
Used to execute multiline python code wont persist states so run everything once.
Do not pass in Markdown just a normal python string (Important)
Try to run all the code at once
Use tools if you think you need help or to confirm answer. Make sure arguments are loadable by json.loads (Super important) use double quotes or it will cause error
These are the libraries you have access to.
Use print statement to print data.
You will not run unsafe code or perform harm to the server youre on. Or import potentially harmful libraries (Very Important).
Libraries: {libraries}
Do not import libraries that are not allowed.
        """

        def extract_python_code(text: str) -> List[str]:
            """
            Extract Python code blocks from a given text.

            Parameters:
                text (str): The input text containing Python code blocks.

            Returns:
                List[str]: A list of Python code blocks.
            """
            # Regular expression to match Python code blocks enclosed in triple backticks
            pattern = r"```python\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            joined_matches = "\n".join(matches)
            return joined_matches or text.strip()

        def python_function(code: str):
            result = self.python_client.evaluate_code(extract_python_code(code))
            try:
                return result["result"]
            except Exception as e:
                return result

        return [Tool("python", python_function, description)]

    def make_agent(
        self,
        llm: BaseChatModel,
        chat_history_messages: list[BaseMessage],
        prompt_args: dict,
        extra_tools: list[Tool] = [],
    ) -> AgentExecutor:
        agent_kwargs = {
            "system_message": SystemMessagePromptTemplate.from_template(
                template="""
You are {ai_name}, an AI teacher designed to teach students. 
You are to take the tone of a teacher.
You must answer the human in {language} (important)
Talk as if you're a teacher. Use the data provided to answer user questions. 

Rules:
    Use file data to answer questions 
    You will not run unsafe code or perform harm to the server youre on. Or import potentially harmful libraries (Very Important).
    Do not return python code to the user.(Super important)
    Use tools if you think you need help or to confirm answer.
    

File content/ Help data/ Student data (This data is from files/subjects the human has provided and can be from webpages, youtube links, files, images and much more):
==========
{help_data}
==========

Use files data above ^^ to answer questions always (important)

Lets use tools and keep the files data above in mind before answering the questions. Good luck mr teacher
"""
            ).format(**prompt_args),
            "extra_prompt_messages": chat_history_messages,
        }
        return self.initialize_agent(
            [*self.make_code_runner(), *extra_tools, *self.base_tools],
            llm,
            agent_kwargs=agent_kwargs,
            max_iterations=4,
        )
        
    def make_unique_by_page_content(self, pages: List[Document]) -> List[Document]:
        unique_pages = {}
        for page in pages:
            if page.page_content not in unique_pages:
                unique_pages[page.page_content] = page
        return list(unique_pages.values())

    def initialize_agent(
        self,
        tools: Sequence[BaseTool],
        llm: BaseLanguageModel,
        callback_manager: Optional[BaseCallbackManager] = None,
        agent_kwargs: Optional[dict] = None,
        **kwargs: Any,
    ):
        agent_obj = OpenAIFunctionsAgent.from_llm_and_tools(
            llm, tools, callback_manager=callback_manager, **agent_kwargs
        )
        return AgentExecutor.from_agent_and_tools(
            agent=agent_obj,
            tools=tools,
            callback_manager=callback_manager,
            **kwargs,
        )

    def query_data(
        self, query: str, collection_name: str, k: int, metadata: Dict[str, str] = None
    ):
        vectorstore = Qdrant(self.client, collection_name, self.embeddings)
        return vectorstore.similarity_search(query, k, filter=metadata)

    def run_agent(
        self,
        prompt: str,
        collection_name: str,
        language: str,
        llm: BaseChatModel,
        callback: callable = None,
        on_end_callback: callable = None,
        chat_history: list[tuple[str, str]] = None,
        metadata: dict[str, str] = None,
        filename: str = None,
        k: int = 5,
    ):
        if chat_history is None:
            chat_history = []
            
        if metadata is None:
            metadata = {}

        if filename:
            metadata["file"] = filename

        combined = (
            self.format_messages(
                chat_history=chat_history,
                tokens_limit=self.conversation_limit,
                human_only=True,
                llm=llm,
                ai_name=self.ai_name,
            )
            + "\n"
            + f"Human: {prompt}"
        )
        similar_docs = self.query_data(
            combined, collection_name, metadata=metadata, k=k
        )
        similar_docs.extend(
            self.query_data(prompt, collection_name, metadata=metadata, k=k)
        )
        similar_docs = self.make_unique_by_page_content(similar_docs)
        similar_docs = self._reduce_tokens_below_limit(
            similar_docs, llm=llm, docs_limit=self.docs_limit
        )
        help_data = "\n".join([doc.page_content for doc in similar_docs])
        
        agent = self.make_agent(
            llm=llm,
            chat_history_messages=self.format_messages_into_messages(
                chat_history, self.conversation_limit, llm
            ),
            prompt_args={
                "language": language,
                "ai_name": self.ai_name,
                "help_data": help_data
            },
            extra_tools=[]
        )
        if not callback:
            raise ValueError("Callback not passed for streaming to work")
        

        return agent.run(
            f"{prompt}, System : Use file content above to get help if needed",
            callbacks=[CustomCallbackAgent(callback, on_end_callback)],
        )

    def chat(
        self,
        collection_name: str,
        prompt: str,
        chat_history: list[tuple[str, str]],
        language: str,
        llm: BaseChatModel,
        callback_func: callable = None,
        on_end_callback: callable = None,
        k: int = 5,
        metadata: dict[str, str] = None,
        filename: str = None,
    ) -> str:
        if metadata is None:
            metadata = {}

        llm.callbacks = [CustomCallback(callback_func, on_end_callback)]
        
        conversation = self.format_messages(
            chat_history=chat_history,
            tokens_limit=self.conversation_limit,
            ai_name=self.ai_name,
            llm=llm,
        )
        combined = (
            self.format_messages(
                chat_history=chat_history,
                tokens_limit=self.conversation_limit,
                human_only=True,
                llm=llm,
                ai_name=self.ai_name,
            )
            + "\n"
            + f"Human: {prompt}"
        )
        if filename:
            metadata["file"] = filename

        similar_docs = self.query_data(
            combined, collection_name, metadata=metadata, k=k // 2
        )
        similar_docs.extend(
            self.query_data(prompt, collection_name, metadata=metadata, k=k // 2)
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
            model_name="gpt",
        )

    def format_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
        human_only: bool = False,
        ai_name: str = "AcademiAi",
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

    def format_messages_into_messages(
        self,
        chat_history: List[Tuple[str, str]],
        tokens_limit: int,
        llm: BaseChatModel,
    ) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        tokens_used: int = 0

        for human_msg, ai_msg in reversed(chat_history):
            human_tokens = llm.get_num_tokens(human_msg)
            ai_tokens = llm.get_num_tokens(ai_msg)
            if tokens_used + ai_tokens <= tokens_limit:
                messages.append(AIMessage(content=ai_msg))
                tokens_used += ai_tokens

            # Add the human message if it doesn't exceed the limit.
            if tokens_used + human_tokens <= tokens_limit:
                messages.append(HumanMessage(content=human_msg))
                tokens_used += human_tokens
            else:
                break  # If we can't add a human message, we have reached the token limit.

        logging.info(f"Chat history: {list(reversed(messages))}")
        return list(reversed(messages))

    def _reduce_tokens_below_limit(
        self, docs: list, docs_limit: int, llm: BaseChatModel
    ) -> list[Document]:
        random.shuffle(docs)
        num_docs = len(docs)
        tokens = [llm.get_num_tokens(doc.page_content) for doc in docs]
        token_count = sum(tokens[:num_docs])
        while token_count > docs_limit:
            num_docs -= 1
            token_count -= tokens[num_docs]

        return docs[:num_docs]


class ChatManagerNonRetrieval(ChatManagerRetrieval):
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """
You are {ai_name}, an AI teacher designed to teach students. You are {model_name} 
You are to take the tone of a teacher.
Talk as if you're a teacher.
in the app you are in students can make quizzes, flashcards and do a lot of cool stuff using ai for coins as currency.
Only return the next message content in {language}. dont return anything else not even the name of AI.
You must answer the human in {language} (important)
"""
            ),
            HumanMessagePromptTemplate.from_template(
                """
Let's think in a step by step, answer the humans question in {language}.

{conversation}

Human: {question}

{ai_name} ({language}):"""
            ),
        ],
        input_variables=[
            "ai_name",
            "conversation",
            "question",
            "language",
            "model_name",
        ],
    )
    
    def __init__(
        self,
        embeddings: Embeddings,
        conversation_limit: int,
        python_client: PythonClient,
        ai_name: str = "AcademiAI",
        base_tools: list[Tool] = [],
    ) -> None:
        self.embeddings = embeddings
        self.conversation_limit = conversation_limit
        self.ai_name = ai_name
        self.python_client = python_client
        self.base_tools = base_tools

    def make_agent(
        self,
        llm: BaseChatModel,
        chat_history_messages: list[BaseMessage],
        prompt_args: dict,
        extra_tools: list[Tool] = [],
    ) -> AgentExecutor:
        agent_kwargs = {
            "system_message": SystemMessagePromptTemplate.from_template(
                template="""
You are {ai_name}, an AI teacher designed to teach students. 
You are to take the tone of a teacher.
You must answer the human in {language} (important)
Talk as if you're a teacher. Use the data provided to answer user questions. 
in the app you are in students can make quizzes, flashcards, write essays, solve questions and do a lot of cool stuff using ai for coins as currency.

Rules:
    Use tools if you think you need help or to confirm answer.

Student has also made subjects in the app and added files to them also.
They are:
{files}
==========

Lets keep tools in mind before answering the questions. Good luck mr teacher
Talk like a teacher, dont start with "Hello, how can i assist you today?". Say what a teacher would
"""
            ).format(**prompt_args),
            "extra_prompt_messages": chat_history_messages,
        }
        return self.initialize_agent(
            [*self.make_code_runner(), *extra_tools, *self.base_tools],
            llm,
            agent_kwargs=agent_kwargs,
            max_iterations=3,
        )
        
    def run_agent(
        self,
        prompt: str,
        language: str,
        llm: BaseChatModel,
        callback: callable = None,
        on_end_callback: callable = None,
        chat_history: list[tuple[str, str]] = None,
        extra_tools: list = None,
        files: str = ""
    ):
        if extra_tools is None:
            extra_tools = []
            
        if chat_history is None:
            chat_history = []
        
        agent = self.make_agent(
            llm=llm,
            chat_history_messages=self.format_messages_into_messages(
                chat_history, self.conversation_limit, llm
            ),
            prompt_args={
                "language": language,
                "ai_name": self.ai_name,
                "files" : files
            },
            extra_tools=extra_tools
        )
        if not callback:
            raise ValueError("Callback not passed for streaming to work")
        
        return agent.run(
            prompt,
            callbacks=[CustomCallbackAgent(callback, on_end_callback)],
        )
        
    def chat(
        self,
        prompt: str,
        chat_history: list[tuple[str, str]],
        language: str,
        llm: BaseChatModel,
        callback_func: callable = None,
        on_end_callback: callable = None,
    ) -> str:

        llm.callbacks = [CustomCallback(callback_func, on_end_callback)]
        
        conversation = self.format_messages(
            chat_history=chat_history,
            tokens_limit=self.conversation_limit,
            ai_name=self.ai_name,
            llm=llm,
        )
        chain = LLMChain(llm=llm, prompt=self.prompt)
        return chain.run(
            ai_name=self.ai_name,
            conversation=conversation,
            question=prompt,
            language=language,
            model_name="gpt",
        )