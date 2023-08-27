from .firebase import *
from .config import *
from langchain.embeddings import OpenAIEmbeddings
from .lib.database import (
    FileDBManager,
    CollectionDBManager,
    UserDBManager,
)
from .lib.knowledge_manager import KnowledgeManager, ChatManager
from langchain.chat_models import ChatOpenAI
import langchain


langchain.verbose = True
user_manager = UserDBManager()
collection_manager = CollectionDBManager()
file_manager = FileDBManager()
knowledge_manager = KnowledgeManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_APIKEY),
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    connection_string=CON_STRING
)
chat_manager = ChatManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_APIKEY),
    ChatOpenAI,
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "temperature" : 0.3},
    connection_string=CON_STRING,
    conversation_limit=700,
    docs_limit=3000,
)

