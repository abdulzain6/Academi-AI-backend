from api.lib.uml_diagram_maker import PlantUML
from .config import *
from .lib.anyscale_embeddings import AnyscaleEmbeddings
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
from langchain.chat_models.base import BaseChatModel
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
from langchain.chat_models.azure_openai import AzureChatOpenAI
from .lib.purchases_play_store import SubscriptionChecker
from .global_tools import CHAT_TOOLS
from .ai_model import AIModel
from contextlib import suppress
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from .lib.email_integrity_checker import EmailIntegrityChecker
import langchain
import redis
import logging



langchain.verbose = False
current_directory = os.path.dirname(os.path.abspath(__file__))
global_kwargs = {"request_timeout": 60, "max_retries": 4}
global_chat_model = AIModel(
    regular_model=ChatOpenAI,
    regular_args={"model_name": "gpt-3.5-turbo-1106"},
    premium_model=ChatOpenAI,
    premium_args={"model_name": "gpt-4-1106-preview", "max_tokens": 2700},
)

global_chat_model_alternative = AIModel(
    regular_model=ChatAnyscale,
    regular_args={"model_name": "mistralai/Mixtral-8x7B-Instruct-v0.1", "max_tokens": 7000},
    premium_model=ChatOpenAI,
    premium_args={"model_name": "gpt-4-1106-preview", "max_tokens": 2700},
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


def get_model(
    model_kwargs: dict,
    stream: bool,
    is_premium: bool,
    alt: bool = False,
    cache: bool = True,
) -> BaseChatModel:
    args = {**model_kwargs, **{"streaming": stream, "cache": cache}}

    if not alt:
        if is_premium:
            model = global_chat_model.premium_model(
                **global_chat_model.premium_args, **global_kwargs
            )
        else:
            model = global_chat_model.regular_model(
                **global_chat_model.regular_args, **global_kwargs
            )
    else:
        if is_premium:
            model = global_chat_model_alternative.premium_model(
                **global_chat_model_alternative.premium_args, **global_kwargs
            )
        else:
            model = global_chat_model_alternative.regular_model(
                **global_chat_model_alternative.regular_args, **global_kwargs
            )


    for k, v in args.items():
        with suppress(Exception):
            setattr(model, k, v)

    fallbacks = []
    for fallback in fallback_chat_models:
        try:
            if is_premium:
                fallback_model = fallback.premium_model(
                    **fallback.premium_args, **global_kwargs
                )
            else:
                fallback_model = fallback.regular_model(
                    **fallback.regular_args, **global_kwargs
                )

            for k, v in args.items():
                with suppress(Exception):
                    setattr(fallback_model, k, v)
            try:
                fallbacks.append(fallback_model)
            except Exception as e:
                logging.error(f"Error in fallback {e}")
        except Exception:
            pass

        logging.info(f"\nAdding fallback {fallback_model}\n")

    logging.info(f"Model used : {model}")
    return model.with_fallbacks(fallbacks=fallbacks)


def get_model_and_fallback(
    model_kwargs: dict, stream: bool, is_premium: bool, alt: bool = False
):
    model_kwargs = {**model_kwargs, "streaming": stream}
    if is_premium:
        if not alt:
            model = global_chat_model.premium_model(
                **global_chat_model.premium_args, **global_kwargs
            )
        else:
            model = global_chat_model_alternative.premium_model(
                **global_chat_model_alternative.premium_args, **global_kwargs
            )

        fallback_model = fallback_chat_models[-1].premium_model(
            **fallback_chat_models[-1].premium_args, **global_kwargs
        )
    else:
        if not alt:
            model = global_chat_model.regular_model(
                **global_chat_model.regular_args, **global_kwargs
            )
        else:
            model = global_chat_model_alternative.regular_model(
                **global_chat_model_alternative.regular_args, **global_kwargs
            )
                
        fallback_model = fallback_chat_models[-1].regular_model(
            **fallback_chat_models[-1].regular_args, **global_kwargs
        )
            
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


# OCR
text_ocr = AzureOCR(AZURE_OCR_ENDPOINT, AZURE_OCR_KEY)
knowledge_manager = KnowledgeManager(
    AnyscaleEmbeddings(
        base_url="https://api.endpoints.anyscale.com/v1",
        model="thenlper/gte-large",
        timeout=10,
        max_retries=2
    ),
    unstructured_api_key=UNSTRUCTURED_API_KEY,
    unstructured_url=UNSTRUCTURED_URL,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
    azure_ocr=text_ocr,
    azure_form_rec_client=DocumentAnalysisClient(
        endpoint=DOC_INTELLIGENCE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DOC_INTELLIGENCE_KEY),
    ),
)
chat_manager = ChatManagerRetrieval(
    AnyscaleEmbeddings(
        base_url="https://api.endpoints.anyscale.com/v1",
        model="thenlper/gte-large",
        timeout=10,
        max_retries=2
    ),
    conversation_limit=800,
    docs_limit=2100,
    qdrant_api_key=QDRANT_API_KEY,
    qdrant_url=QDRANT_URL,
)
chat_manager_agent_non_retrieval = ChatManagerNonRetrieval(
    AnyscaleEmbeddings(
        base_url="https://api.endpoints.anyscale.com/v1",
        model="thenlper/gte-large",
        timeout=10,
        max_retries=2
    ),
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

plantuml_server = PlantUML(url=PLANTUML_URL)

# Monetization
user_points_manager = UserPointsManager(MONGODB_URL, DATABASE_NAME, DEFAULT_POINTS)
referral_manager = ReferralManager(
    user_manager, user_points_manager, DEFAULT_REFERRAL_POINTS
)
credentials_path = os.path.join(
    current_directory, "creds", "academi-ai-6173d917c2a1.json"
)
subscription_checker = SubscriptionChecker(credentials_path)


#email Intergrity checker
email_checker = EmailIntegrityChecker()