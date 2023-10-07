from .config import *
from langchain.embeddings import OpenAIEmbeddings
from .lib.database import (
    FileDBManager,
    CollectionDBManager,
    UserDBManager,
    MessageDBManager,
    UserPointsManager,
    ReferralManager
)
from .lib.knowledge_manager import KnowledgeManager, ChatManager
from .lib.presentation_maker.database import initialize_managers
from .lib.presentation_maker.image_gen import PexelsImageSearch
from .lib.presentation_maker.presentation_maker import PresentationMaker
from .lib.quiz import QuizGenerator
from .lib.maths_solver.agent import MathSolver
from .lib.maths_solver.python_exec_client import PythonClient, Urls
from .lib.maths_solver.ocr import ImageOCR
from .lib.writer import Writer
from .lib.redis_cache import RedisCache
from langchain.chat_models import ChatOpenAI
from langchain.llms import OpenAI
import langchain
import redis


langchain.verbose = True
langchain.llm_cache = RedisCache(redis_=redis.from_url(REDIS_URL), ttl=CACHE_TTL)
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
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "temperature": 0.3, "request_timeout" : 100},
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
        "request_timeout" : 100
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
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "temperature": 0.3, "request_timeout" : 100},
)
image_ocr = ImageOCR(
    app_id=MATHPIX_APPID,
    app_key=MATHPIX_API_KEY,
    llm_kwargs={"openai_api_key": OPENAI_APIKEY, "model": "gpt-3.5-turbo-instruct", "request_timeout" : 100},
    llm_cls=OpenAI,
)
writer = Writer(
    ChatOpenAI,
    llm_kwargs={
        "model_name": "gpt-3.5-turbo",
        "temperature": 0.3,
        "openai_api_key": OPENAI_APIKEY,
        "request_timeout" : 100
    },
)
user_points_manager = UserPointsManager(MONGODB_URL, DATABASE_NAME, DEFAULT_POINTS)
referral_manager = ReferralManager(user_manager, user_points_manager, DEFAULT_REFERRAL_POINTS)