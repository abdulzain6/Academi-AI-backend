from .config import *
from langchain.embeddings import OpenAIEmbeddings
from .lib.database import (
    FileDBManager,
    CollectionDBManager,
    UserDBManager,
    MessageDBManager,
    UserPointsManager,
    ReferralManager,
)
from .lib.database.purchases import (
    SubscriptionFeatures,
    SubscriptionType,
    SubscriptionManager,
    MonthlyCoinsFeature,
    IncrementalFeature,
    StaticFeature,
    MonthlyLimitFeature,
)
from .lib.database.cache_manager import RedisCacheManager
from .lib.knowledge_manager import KnowledgeManager, ChatManager
from .lib.presentation_maker.database import initialize_managers
from .lib.maths_solver.python_exec_client import PythonClient, Urls
from .lib.maths_solver.ocr import ImageOCR
from .lib.summary_writer import SummaryWriter
from .lib.redis_cache import RedisCache
from langchain.chat_models import ChatOpenAI
from langchain.llms import OpenAI
from .lib.purchases_play_store import SubscriptionChecker
import langchain
import redis


langchain.verbose = True
current_directory = os.path.dirname(os.path.abspath(__file__))


langchain.llm_cache = RedisCache(redis_=redis.from_url(REDIS_URL), ttl=CACHE_TTL)
redis_cache_manager = RedisCacheManager(redis.from_url(REDIS_URL))

# Database Managers
collection_manager = CollectionDBManager(
    MONGODB_URL,
    DATABASE_NAME,
    cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
)
user_manager = UserDBManager(
    MONGODB_URL,
    DATABASE_NAME,
    cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
    collection_manager=collection_manager
)
file_manager = FileDBManager(MONGODB_URL, DATABASE_NAME, collection_manager)
conversation_manager = MessageDBManager(
    MONGODB_URL, DATABASE_NAME, collection_manager, file_manager
)

knowledge_manager = KnowledgeManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    unstructured_url=UNSTRUCTURED_URL,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
chat_manager = ChatManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
    ChatOpenAI,
    llm_kwargs={
        "openai_api_key": OPENAI_API_KEY,
        "temperature": 0.3,
        "request_timeout": 100,
    },
    conversation_limit=700,
    docs_limit=3000,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
subscription_manager = SubscriptionManager(
    connection_string=MONGODB_URL,
    database_name=DATABASE_NAME,
    user_points_manager=UserPointsManager(
        connection_string=MONGODB_URL,
        database_name=DATABASE_NAME,
    ),
    plan_features={
        SubscriptionType.FREE: SubscriptionFeatures(
            incremental=[
                IncrementalFeature(name="PRESENTATION", limit=2),
                IncrementalFeature(name="QUIZ", limit=3),
                IncrementalFeature(name="OCR", limit=3),
            ],
            static=[StaticFeature(name="ppt_pages", value=12)],
            monthly_limit=[],
            monthly_coins=MonthlyCoinsFeature(amount=0),
        ),
        SubscriptionType.LITE: SubscriptionFeatures(
            incremental=[
                IncrementalFeature(name="PRESENTATION", limit=6),
                IncrementalFeature(name="OCR", limit=10),
            ],
            static=[StaticFeature(name="ppt_pages", value=12)],
            monthly_limit=[],
            monthly_coins=MonthlyCoinsFeature(amount=150),
        ),
        SubscriptionType.PRO: SubscriptionFeatures(
            incremental=[],
            static=[StaticFeature(name="ppt_pages", value=20)],
            monthly_limit=[],
            monthly_coins=MonthlyCoinsFeature(amount=500),
        ),
        SubscriptionType.ELITE: SubscriptionFeatures(
            incremental=[],
            static=[StaticFeature(name="ppt_pages", value=20)],
            monthly_limit=[
                MonthlyLimitFeature(
                    name="MODEL",
                    limit=75,
                    value="gpt-4",
                    fallback_value="gpt-3.5-turbo",
                    enabled=True,
                )
            ],
            monthly_coins=MonthlyCoinsFeature(amount=2500),
        ),
    },
    redis_client=redis.from_url(REDIS_URL),
)


# llms

global_chat_model = ChatOpenAI
global_chat_model_kwargs = {"request_timeout": 150}


# Presentation

template_manager, temp_knowledge_manager = initialize_managers(
    MONGODB_URL, DATABASE_NAME, local_storage_path="/tmp/ppts"
)


# Maths Solver

client = PythonClient(
    Urls(
        main_url=MAIN_URL_EXECUTOR,
        evaluate_url=EVALUATE_URL_EXECUTOR,
        available_libraries_url=AVAILABLE_LIBRARIES_URL,
    ),
    40,
)
image_ocr = ImageOCR(
    app_id=MATHPIX_APPID,
    app_key=MATHPIX_API_KEY,
    llm_kwargs={
        "openai_api_key": OPENAI_API_KEY,
        "model": "gpt-3.5-turbo-instruct",
        "request_timeout": 100,
    },
    llm_cls=OpenAI,
)


# SUmmary Writer

summary_writer = SummaryWriter(
    ChatOpenAI,
    llm_kwargs={
        "model_name": "gpt-3.5-turbo-16k",
        "temperature": 0.3,
        "openai_api_key": OPENAI_API_KEY,
        "request_timeout": 250,
    },
)


# Monetization


user_points_manager = UserPointsManager(MONGODB_URL, DATABASE_NAME, DEFAULT_POINTS)
referral_manager = ReferralManager(
    user_manager, user_points_manager, DEFAULT_REFERRAL_POINTS
)
credentials_path = os.path.join(
    current_directory, "creds", "academi-ai-6173d917c2a1.json"
)
subscription_checker = SubscriptionChecker(credentials_path)
