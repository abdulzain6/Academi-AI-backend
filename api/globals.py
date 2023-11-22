import logging
from .config import *
from langchain.embeddings import OpenAIEmbeddings
from .lib.ocr import AzureOCR
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
from .lib.knowledge_manager import (
    KnowledgeManager,
    ChatManagerRetrieval,
    ChatManagerNonRetrieval,
)
from .lib.presentation_maker.database import (
    initialize_managers,
    DEFAULT_TEMPLATE_DIR,
    DEFAULT_TEMPLATES_JSON,
)
from .lib.maths_solver.python_exec_client import PythonClient, Urls
from .lib.maths_solver.ocr import ImageOCR
from .lib.redis_cache import RedisCache
from langchain.chat_models import ChatOpenAI, ChatAnyscale
from .lib.purchases_play_store import SubscriptionChecker
from .global_tools import CHAT_TOOLS
from .ai_model import AIModel
from copy import deepcopy
from contextlib import suppress
import langchain
import redis


langchain.verbose = False
current_directory = os.path.dirname(os.path.abspath(__file__))
global_kwargs = {"request_timeout": 50, "max_retries": 4}
global_chat_model = AIModel(
    regular_model=ChatOpenAI(model_name="gpt-3.5-turbo"),
    premium_model=ChatOpenAI(model_name="gpt-4-1106-preview", max_tokens=2700)
)

global_chat_model_alternative = AIModel(
    regular_model=ChatAnyscale(model_name="mistralai/Mistral-7B-Instruct-v0.1"),
    premium_model=ChatOpenAI(model_name="gpt-4-1106-preview", max_tokens=2700)
)

fallback_chat_models = [
    AIModel(
        regular_model=ChatAnyscale(model_name="meta-llama/Llama-2-70b-chat-hf"),
        premium_model=ChatAnyscale(model_name="meta-llama/Llama-2-70b-chat-hf"),
    )
]

def get_model(model_kwargs: dict, stream: bool, is_premium: bool, alt: bool = False):
    args = {**model_kwargs, **{"streaming": stream}}
    
    if not alt:
        if is_premium:
            model = deepcopy(global_chat_model.premium_model)
        else:
            model = deepcopy(global_chat_model.regular_model)
    else:
        if is_premium:
            model = deepcopy(global_chat_model_alternative.premium_model)
        else:
            model = deepcopy(global_chat_model_alternative.regular_model)
            
    for k, v in args.items():
        with suppress(Exception):
            setattr(model, k, v)

    fallbacks = []
    for fallback in fallback_chat_models:
        if is_premium:
            fallback_model = deepcopy(fallback.premium_model)
        else:
            fallback_model = deepcopy(fallback.regular_model)

        for k, v in args.items():
            with suppress(Exception):
                setattr(fallback_model, k, v)
        try:
            fallbacks.append(fallback_model)
        except Exception as e:
            logging.error(f"Error in fallback {e}")
            
        logging.info(f"\nAdding fallback {fallback_model}\n")

    logging.info(f"Model used : {model}")
    return model.with_fallbacks(fallbacks=fallbacks)


def get_model_and_fallback(model_kwargs: dict, stream: bool, is_premium: bool, alt: bool = False):
    model_kwargs = {**model_kwargs, "streaming" : stream}
    if is_premium:
        if not alt:
            model = deepcopy(global_chat_model.premium_model)
        else:
            model = deepcopy(global_chat_model_alternative.premium_model)
            
        fallback_model = fallback_chat_models[-1].premium_model
    else:
        if not alt:
            model = deepcopy(global_chat_model.regular_model)
        else:
            model = deepcopy(global_chat_model_alternative.regular_model)
            
        fallback_model = deepcopy(fallback_chat_models[-1].regular_model)

    for k, v in model_kwargs.items():
        with suppress(Exception):
            setattr(model, k, v)
        with suppress(Exception):
            setattr(fallback_model, k, v)
    
    return model, fallback_model
    

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
    conversation_limit=800,
    docs_limit=1700,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
    python_client=client,
)
chat_manager_agent_non_retrieval = ChatManagerNonRetrieval(
    OpenAIEmbeddings(),
    conversation_limit=700,
    python_client=client,
    base_tools=CHAT_TOOLS,
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
    template_json_path=DEFAULT_TEMPLATES_JSON, template_dir=DEFAULT_TEMPLATE_DIR
)


# Maths Solver
image_ocr = ImageOCR(
    app_id=MATHPIX_APPID,
    app_key=MATHPIX_API_KEY,
)

# OCR
text_ocr = AzureOCR(AZURE_OCR_ENDPOINT, AZURE_OCR_KEY)

# Monetization
user_points_manager = UserPointsManager(MONGODB_URL, DATABASE_NAME, DEFAULT_POINTS)
referral_manager = ReferralManager(
    user_manager, user_points_manager, DEFAULT_REFERRAL_POINTS
)
credentials_path = os.path.join(
    current_directory, "creds", "academi-ai-6173d917c2a1.json"
)
subscription_checker = SubscriptionChecker(credentials_path)
