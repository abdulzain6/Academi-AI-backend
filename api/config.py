import json
import os
from typing import Dict
from dotenv import load_dotenv
from api.lib.database.purchases import SubscriptionType


load_dotenv()


def get_dict_from_env_var(env_var_name: str, default: Dict = None) -> Dict:
    env_val = os.environ.get(env_var_name)
    return json.loads(env_val) if env_val is not None else default


UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", None)
UNSTRUCTURED_URL = os.getenv("UNSTRUCTURED_URL", "http://localhost:8080/general/v0/general")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_URL = os.getenv("QDRANT_URL", "localhost")
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "study-app")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
QUIZ_MAX_API_CALLS = int(os.getenv("QUIZ_MAX_API_CALLS", 4))

MAIN_URL_EXECUTOR = os.getenv("MAIN_URL_EXECUTOR", "http://127.0.0.1:9000/")
EVALUATE_URL_EXECUTOR = os.getenv("EVALUATE_URL_EXECUTOR", "http://127.0.0.1:9000/evaluate")
AVAILABLE_LIBRARIES_URL = os.getenv("AVAILABLE_LIBRARIES_URL", "http://127.0.0.1:9000/allowed_libraries")
MATHPIX_APPID = os.getenv("MATHPIX_APPID")
MATHPIX_API_KEY = os.getenv("MATHPIX_API_KEY")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 250))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", 5 * 24 * 60 * 60))
DEFAULT_POINTS = int(os.getenv("DEFAULT_POINTS", 15))
FEATURE_PRICING = get_dict_from_env_var(
    "FEATURE_PRICING", 
    {
        "QUIZ" : 3,
        "CHAT" : 1,
        "OCR" : 1,
        "PRESENTATION" : 4,
        "FLASHCARDS" : 2,
        "WRITER" : 2,
        "SUMMARY" : 2,
        "CV" : 3,
        "NOTES" : 3,
        "GRAMMAR" : 2
    }
)

DEFAULT_POINTS_INCREMENT = int(os.getenv("DEFAULT_POINTS_INCREMENT", 2))
DEFAULT_REFERRAL_POINTS = int(os.getenv("DEFAULT_REFERRAL_POINTS", 15))
FILE_COLLECTION_LIMITS = {
    SubscriptionType.FREE : 4
}
APP_PACKAGE_NAME = "com.ainnovate.academiaii"
PRODUCT_ID_MAP = {
    'lite_monthly' : SubscriptionType.LITE,
    'lite_6_monthly' :SubscriptionType.LITE,
    'lite_yearly' : SubscriptionType.LITE,
    'pro_monthly' : SubscriptionType.PRO,
    'pro_6_monthly' : SubscriptionType.PRO,
    'pro_yearly': SubscriptionType.PRO,
    'elite_monthly' : SubscriptionType.ELITE,
    'elite_6_monthly' : SubscriptionType.ELITE,
    'elite_yearly' : SubscriptionType.ELITE,
}
DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "zaighamnet")
DOCS_USERNAME = os.getenv("DOCS_USERNAME", "chutikr")
PROM_USERNAME = os.getenv("PROM_USERNAME", "PROM_MONITO_MY_APP_U_M0RON_BE_N!CE")
PROM_PASSWORD = os.getenv("PROM_PASSWORD", "ABRACADABRA_KAZAMM_HEHE_@#$")
CRONJOB_KEY = os.getenv("CRONJOB_KEY", "ABRACADABRA_KAZAMM_HEHE_@#$")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")
CACHE_DOCUMENT_URL_TEMPLATE = os.getenv("CACHE_DOCUMENT_URL_TEMPLATE", "http://www.api.academiai.org/api/v1/tools/document/{doc_id}")