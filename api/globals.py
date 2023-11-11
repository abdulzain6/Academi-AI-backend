#from .telemetery import *
import logging
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
from .lib.knowledge_manager import KnowledgeManager, ChatManagerRetrieval, ChatManagerNonRetrieval
from .lib.presentation_maker.database import initialize_managers
from .lib.maths_solver.python_exec_client import PythonClient, Urls
from .lib.maths_solver.ocr import ImageOCR
from .lib.redis_cache import RedisCache
from langchain.chat_models import ChatOpenAI, ChatAnyscale
from .lib.purchases_play_store import SubscriptionChecker
from .global_tools import CHAT_TOOLS
import langchain
import redis


langchain.verbose = False
current_directory = os.path.dirname(os.path.abspath(__file__))




global_chat_model_kwargs = {"request_timeout": 150, "max_retries": 0, "max_tokens" : 1700}
global_chat_model = (ChatOpenAI, {"model_name" : "gpt-3.5-turbo"}, {"model_name" : "gpt-4-1106-preview"})
# Model class , free overrides, premium overides
fallback_chat_models = [
    (
        ChatAnyscale,
        {"model_name": "meta-llama/Llama-2-70b-chat-hf"},
        {"model_name": "meta-llama/Llama-2-70b-chat-hf"},
    )
]

try:
    langchain.llm_cache = RedisCache(redis_=redis.from_url(REDIS_URL), ttl=CACHE_TTL)
except Exception:
    logging.info("Fix redis cache")
try:
    redis_cache_manager = RedisCacheManager(redis.from_url(REDIS_URL))
except Exception:
    redis_cache_manager = RedisCacheManager(None)


# code runner
client = PythonClient(
    Urls(
        main_url=MAIN_URL_EXECUTOR,
        evaluate_url=EVALUATE_URL_EXECUTOR,
        available_libraries_url=AVAILABLE_LIBRARIES_URL,
    ),
    40,
)

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
    collection_manager=collection_manager,
)
file_manager = FileDBManager(
    MONGODB_URL,
    DATABASE_NAME,
    collection_manager,
    cache=RedisCacheManager(redis.from_url(REDIS_URL)),
)
conversation_manager = MessageDBManager(
    MONGODB_URL,
    DATABASE_NAME,
    collection_manager,
    file_manager,
    cache_manager=RedisCacheManager(redis.from_url(REDIS_URL), 50000),
)

knowledge_manager = KnowledgeManager(
    OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    unstructured_url=UNSTRUCTURED_URL,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
chat_manager = ChatManagerRetrieval(
    OpenAIEmbeddings(),
    conversation_limit=700,
    docs_limit=1000,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
    python_client=client,
)
chat_manager_agent_non_retrieval = ChatManagerNonRetrieval(
    OpenAIEmbeddings(),
    conversation_limit=700,
    python_client=client,
    base_tools=CHAT_TOOLS
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
                    value="paid",
                    fallback_value="free",
                    enabled=True,
                )
            ],
            monthly_coins=MonthlyCoinsFeature(amount=2000),
        ),
    },
    cache_manager=RedisCacheManager(redis.from_url(REDIS_URL), ttl=3600),
)


# Presentation

template_manager, temp_knowledge_manager = initialize_managers(
    MONGODB_URL, DATABASE_NAME, local_storage_path="/tmp/ppts"
)


# Maths Solver
image_ocr = ImageOCR(
    app_id=MATHPIX_APPID,
    app_key=MATHPIX_API_KEY,
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
