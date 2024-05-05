from api.lib.uml_diagram_maker import PlantUML
from .config import *
from .lib.ocr import AzureOCR
from .lib.database import (
    FileDBManager,
    CollectionDBManager,
    UserDBManager,
    MessageDBManager,
    UserPointsManager,
    ReferralManager,
    MongoLogManager
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
from langchain.chat_models.base import BaseChatModel
from .lib.database.cache_manager import RedisCacheManager
from .lib.database.rotating_redis_list import RotatingRedisList
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
from langchain_openai.chat_models import ChatOpenAI
from langchain_openai import AzureChatOpenAI
from .lib.purchases_play_store import SubscriptionChecker
from .ai_model import AIModel
from contextlib import suppress
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from .lib.email_integrity_checker import EmailIntegrityChecker
from .lib.mermaid_maker import MermaidClient
from .lib.embeddings import TogetherEmbeddingsParallel
from langchain_groq import ChatGroq


import langchain
import redis
import logging



langchain.verbose = False

try:
    langchain.llm_cache = RedisCache(redis_=redis.from_url(REDIS_URL), ttl=CACHE_TTL)
except Exception:
    logging.info("Fix redis cache")
    
try:
    redis_cache_manager = RedisCacheManager(redis.from_url(REDIS_URL))
except Exception:
    redis_cache_manager = RedisCacheManager(None)
    
try:
    rotating_list = RotatingRedisList(redis.from_url(REDIS_URL), "api_keys", GROQ_API_KEYS)
except Exception:
    rotating_list = RotatingRedisList(None, "api_keys", GROQ_API_KEYS)

global_chat_model = AIModel(
    regular_model=ChatOpenAI,
    regular_args={"max_tokens": 2700, "request_timeout": 60, "model_name" : "gpt-3.5-turbo-0125"},
    premium_model=ChatOpenAI,
    premium_args={"model_name": "gpt-4-1106-preview", "max_tokens": 2700, "request_timeout": 60, "max_retries": 4},
)

global_chat_model_alternative = AIModel(
    regular_model=ChatGroq,
    regular_args={"max_tokens": 2700, "request_timeout": 60, "model_name" : "llama3-70b-8192"},
    premium_model=ChatOpenAI,
    premium_args={"model_name": "gpt-4-1106-preview", "max_tokens": 2700, "request_timeout": 60, "max_retries": 4},
)

fallback_chat_models = [
    AIModel(
        regular_model=AzureChatOpenAI,
        regular_args={
            "openai_api_version": "2023-05-15",
            "model": "gpt-35-turbo",
            "azure_deployment": "academi",
        },
        premium_model=AzureChatOpenAI,
        premium_args={
            "openai_api_version": "2023-05-15",
            "model": "gpt-35-turbo",
            "azure_deployment": "academi",
        },
    )
]



def create_model(model_class: AIModel, premium: bool, model_kwargs: dict, together_chat: bool =  False) -> BaseChatModel:
    model_type = 'premium' if premium else 'regular'
    args = getattr(model_class, f"{model_type}_args")
    if getattr(model_class, f"{model_type}_model") is ChatGroq:
        key = rotating_list.get_item()
        logging.info(f"Using {key} for groq")
        args["groq_api_key"] = key
    return getattr(model_class, f"{model_type}_model")(**args, **model_kwargs)

def set_model_attributes(model: BaseChatModel, attributes: dict):
    for k, v in attributes.items():
        with suppress(Exception):
            setattr(model, k, v)

def get_model(
    model_kwargs: dict,
    stream: bool,
    is_premium: bool,
    alt: bool = False,
    cache: bool = True,
    together_chat: bool = False
) -> BaseChatModel:
    args = {**model_kwargs, "streaming": stream, "cache": cache}
    model_class = global_chat_model_alternative if alt else global_chat_model
    model = create_model(model_class, is_premium, args, together_chat)
    set_model_attributes(model, args)

    fallbacks = []
    for fallback in fallback_chat_models:
        try:
            fallback_model = create_model(fallback, is_premium, args, together_chat)
            set_model_attributes(fallback_model, args)
            fallbacks.append(fallback_model)
        except Exception as e:
            logging.error(f"Error in fallback {e}")

    return model.with_fallbacks(fallbacks=fallbacks)

def get_model_and_fallback(
    model_kwargs: dict, stream: bool, is_premium: bool, alt: bool = False, together_chat: bool =  False
):
    model_kwargs = {**model_kwargs, "streaming": stream}
    model_class = global_chat_model_alternative if alt else global_chat_model
    fallback_class = fallback_chat_models[-1]

    model = create_model(model_class, is_premium, model_kwargs, together_chat=together_chat)
    fallback_model = create_model(fallback_class, is_premium, model_kwargs, together_chat=together_chat)

    set_model_attributes(model, model_kwargs)
    set_model_attributes(fallback_model, model_kwargs)

    return model, fallback_model





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
log_manager = MongoLogManager(
    uri=MONGODB_URL,
    db_name=DATABASE_NAME,
    collection_name="logs"
)

# OCR
text_ocr = AzureOCR(AZURE_OCR_ENDPOINT, AZURE_OCR_KEY)
knowledge_manager = KnowledgeManager(
    TogetherEmbeddingsParallel(
        timeout=10,
        max_retries=2
    ),
    chunk_size=2250,
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    unstructured_url=UNSTRUCTURED_URL,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
    azure_ocr=text_ocr,
    azure_form_rec_client=DocumentAnalysisClient(
        endpoint=DOC_INTELLIGENCE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DOC_INTELLIGENCE_KEY),
    ),
    qdrant_collection_name="academi"
)
chat_manager = ChatManagerRetrieval(
    TogetherEmbeddingsParallel(
        timeout=10,
        max_retries=2
    ),
    conversation_limit=3000,
    docs_limit=10000,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
chat_manager_agent_non_retrieval = ChatManagerNonRetrieval(
    TogetherEmbeddingsParallel(
        timeout=10,
        max_retries=2
    ),
    conversation_limit=2000,
    python_client=client,
    base_tools=[],
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


image_ocr = ImageOCR()
plantuml_server = PlantUML(url=PLANTUML_URL)
mermaid_client = MermaidClient(server_url=MERMAID_SERVER_URL)

# Monetization
user_points_manager = UserPointsManager(MONGODB_URL, DATABASE_NAME, DEFAULT_POINTS)
referral_manager = ReferralManager(
    user_manager, user_points_manager, DEFAULT_REFERRAL_POINTS
)
current_directory = os.path.dirname(os.path.abspath(__file__))
credentials_path = os.path.join(
    current_directory, "creds", "academi-ai-6173d917c2a1.json"
)
subscription_checker = SubscriptionChecker(credentials_path)


#email Intergrity checker
email_checker = EmailIntegrityChecker()