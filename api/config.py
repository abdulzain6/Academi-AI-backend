import json
import os
from typing import Dict
from dotenv import load_dotenv
from api.lib.database.purchases import SubscriptionType


load_dotenv()


def get_dict_from_env_var(env_var_name: str, default: Dict = None) -> Dict:
    env_val = os.environ.get(env_var_name)
    return json.loads(env_val) if env_val is not None else default


GROQ_API_KEYS = os.getenv("GROQ_API_KEYS", "").split(" ")
UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", None)
UNSTRUCTURED_URL = os.getenv("UNSTRUCTURED_URL", "http://localhost:8080/general/v0/general")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_URL = os.getenv("QDRANT_URL", "localhost")
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "study-app")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
QUIZ_MAX_API_CALLS = int(os.getenv("QUIZ_MAX_API_CALLS", 4))
PLANTUML_URL = os.getenv("PLANTUML_URL", "http://localhost:9080/img/")
MAIN_URL_EXECUTOR = os.getenv("MAIN_URL_EXECUTOR", "http://127.0.0.1:9000/")
EVALUATE_URL_EXECUTOR = os.getenv("EVALUATE_URL_EXECUTOR", "http://127.0.0.1:9000/evaluate")
AVAILABLE_LIBRARIES_URL = os.getenv("AVAILABLE_LIBRARIES_URL", "http://127.0.0.1:9000/allowed_libraries")
MATHPIX_APPID = os.getenv("MATHPIX_APPID")
MATHPIX_API_KEY = os.getenv("MATHPIX_API_KEY")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 1000))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", 5 * 24 * 60 * 60))
DEFAULT_POINTS = int(os.getenv("DEFAULT_POINTS", 20))
FEATURE_PRICING = get_dict_from_env_var(
    "FEATURE_PRICING", 
    {
        "QUIZ" : 3,
        "CHAT" : 1,
        "OCR" : 2,
        "PRESENTATION" : 4,
        "FLASHCARDS" : 3,
        "WRITER" : 2,
        "SUMMARY" : 2,
        "CV" : 3,
        "NOTES" : 3,
        "GRAMMAR" : 2,
        "UML" : 3,
        "GRAPH" : 1
    }
)

DEFAULT_POINTS_INCREMENT = int(os.getenv("DEFAULT_POINTS_INCREMENT", 2))
DEFAULT_REFERRAL_POINTS = int(os.getenv("DEFAULT_REFERRAL_POINTS", 10))
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
SUB_COIN_MAP = {
    'lite_monthly' : 150,
    'lite_6_monthly' : 150 ,
    'lite_yearly' : 150,
    'pro_monthly' : 500,
    'pro_6_monthly' : 500,
    'pro_yearly': 500,
    'elite_monthly' : 2000,
    'elite_6_monthly' : 2000,
    'elite_yearly' : 2000
}
PRODUCT_ID_COIN_MAP = {
    '30_coins_product': 30,
    '50_coins_product' : 50,
    '75_coins_product': 75,
    '100_coins_product': 100,
    '200_coins_product': 200,
    '500_coins_product' : 500,
    '1000_coins_product': 1000,
    '2000_coins_product' : 2000
}
DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "zaighamnet")
DOCS_USERNAME = os.getenv("DOCS_USERNAME", "chutikr")
PROM_USERNAME = os.getenv("PROM_USERNAME", "PROM_MONITO_MY_APP_U_M0RON_BE_N!CE")
PROM_PASSWORD = os.getenv("PROM_PASSWORD", "ABRACADABRA_KAZAMM_HEHE_@#$")
CRONJOB_KEY = os.getenv("CRONJOB_KEY", "ABRACADABRA_KAZAMM_HEHE_@#$")
API_KEY_BACKDOOR = os.getenv("API_KEY_BACKDOOR", "ZAIGHAMNETTTTTTTT!!!CHUTIKRRRR!!!")
AZURE_OCR_ENDPOINT = os.getenv("AZURE_OCR_ENDPOINT")
AZURE_OCR_KEY = os.getenv("AZURE_OCR_KEY")

CACHE_DOCUMENT_URL_TEMPLATE = os.getenv("CACHE_DOCUMENT_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/document/{doc_id}")
CACHE_IMAGE_URL_TEMPLATE = os.getenv("CACHE_IMAGE_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/image/{doc_id}")
CACHE_VIDEO_URL_TEMPLATE = os.getenv("CACHE_VIDEO_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/retrieve_video/{video_id}")


DOC_INTELLIGENCE_ENDPOINT = os.getenv("DOC_INTELLIGENCE_ENDPOINT")
AZURE_DOC_INTELLIGENCE_KEY = os.getenv("AZURE_DOC_INTELLIGENCE_KEY")
SEARCHX_HOST = os.getenv("SEARCHX_HOST", "http://localhost:8090")
APP_DOMAIN = os.getenv("APP_DOMAIN", "https://api.academiai.org")
GET_CV_IMAGES_ENDPOINT = APP_DOMAIN + "/api/v1/cv_maker/get_image/{name}"
MERMAID_SERVER_URL = os.getenv("MERMAID_SERVER_URL")


#GPTS
GPT_API_KEY = os.getenv("GPT_API_KEY", "ZAIGHAMNETTTTTTTT!!1234!!CHUTIKRRRR!!!")
CYCLE_TLS_SERVER_URL = os.getenv("CYCLE_TLS_SERVER_URL", "http://localhost:3000/fetch")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "zain0694-20")
HTTP_PROXY_URL = os.getenv("HTTP_PROXY_URL")