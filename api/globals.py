from .config import *
from langchain.embeddings import OpenAIEmbeddings
from .lib.database import (
    FileDBManager,
    CollectionDBManager,
    UserDBManager,
    MessageDBManager,
)
from .lib.knowledge_manager import KnowledgeManager, ChatManager
from .lib.presentation_maker.database import initialize_managers
from .lib.presentation_maker.image_gen import PexelsImageSearch
from .lib.presentation_maker.presentation_maker import PresentationMaker
from .lib.quiz import QuizGenerator
from .lib.maths_solver.agent import MathSolver
from .lib.maths_solver.python_exec_client import PythonClient, Urls
from langchain.chat_models import ChatOpenAI
import langchain


langchain.verbose = True
user_manager = UserDBManager(MONGODB_URL, DATABASE_NAME)
collection_manager = CollectionDBManager(MONGODB_URL, DATABASE_NAME)
file_manager = FileDBManager(MONGODB_URL, DATABASE_NAME, collection_manager)
conversation_manager = MessageDBManager(MONGODB_URL, DATABASE_NAME)
knowledge_manager = KnowledgeManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_APIKEY),
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    unstructured_url=UNSTRUCTURED_URL,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
chat_manager = ChatManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_APIKEY),
    ChatOpenAI,
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "temperature": 0.3},
    conversation_limit=700,
    docs_limit=3000,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
template_manager, temp_knowledge_manager = initialize_managers(
    OPENAI_APIKEY, MONGODB_URL, DATABASE_NAME, local_storage_path="/tmp/ppts"
)
presentation_maker = PresentationMaker(
    template_manager,
    temp_knowledge_manager,
    OPENAI_APIKEY,
    pexel_image_gen_cls=PexelsImageSearch,
    image_gen_args={"api_key": PEXELS_API_KEY, "image_cache_dir": "/tmp/.image_cache"},
    vectorstore=knowledge_manager,
)
quiz_generator = QuizGenerator(
    file_manager,
    None,
    ChatOpenAI,
    {
        "openai_api_key": OPENAI_APIKEY,
        "temperature": 0.5,
    },
)
client = PythonClient(
    Urls(
        main_url=MAIN_URL_EXECUTOR,
        evaluate_url=EVALUATE_URL_EXECUTOR,
        available_libraries_url=AVAILABLE_LIBRARIES_URL,
    ),
    40,
)
default_llm = ChatOpenAI
maths_solver = MathSolver(
    client,
    default_llm,
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "temperature": 0.2},
)
