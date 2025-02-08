import json
import os
from typing import Dict
from dotenv import load_dotenv
from api.lib.database.purchases import SubscriptionType


load_dotenv()


def get_dict_from_env_var(env_var_name: str, default: Dict = None) -> Dict:
    env_val = os.environ.get(env_var_name)
    return json.loads(env_val) if env_val is not None else default



MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "study-app")
PLANTUML_URL = os.getenv("PLANTUML_URL", "http://localhost:9080/img/")
MAIN_URL_EXECUTOR = os.getenv("MAIN_URL_EXECUTOR", "http://127.0.0.1:9000/")
EVALUATE_URL_EXECUTOR = os.getenv("EVALUATE_URL_EXECUTOR", "http://127.0.0.1:9000/evaluate")
AVAILABLE_LIBRARIES_URL = os.getenv("AVAILABLE_LIBRARIES_URL", "http://127.0.0.1:9000/allowed_libraries")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 1000))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", 5 * 24 * 60 * 60))
DEFAULT_POINTS = int(os.getenv("DEFAULT_POINTS", 75))
FEATURE_PRICING = get_dict_from_env_var(
    "FEATURE_PRICING", 
    {
        "QUIZ" : 4,
        "CHAT" : 1,
        "OCR" : 3,
        "PRESENTATION" : 5,
        "FLASHCARDS" : 3,
        "WRITER" : 2,
        "SUMMARY" : 2,
        "CV" : 3,
        "NOTES" : 4,
        "TEXT_TO_HANDWRITTING" : 3,
        "GRAMMAR" : 2,
        "UML" : 3,
        "ASSIGNMENT" : 25,
        "INFOGRAPHIC" : 2,
        "LECTURE" : 30,
        "IMAGE_EXPLAINERS" : 2
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
SUB_COIN_MAP_REVENUE_CAT = {
    "pro_weekly" : 500,
    "pro_yearly" : 500,
    "pro_yearly:pro-yearly" : 500,
    "pro_weekly:pro-weekly" : 500
}
PRODUCT_ID_MAP_REVENUE_CAT = {
    'pro_weekly' : SubscriptionType.PRO,
    'pro_yearly' : SubscriptionType.PRO,
    "pro_yearly:pro-yearly" : SubscriptionType.PRO,
    "pro_weekly:pro-weekly" : SubscriptionType.PRO
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
REVENUE_CAT_WEBHOOK_TOKEN = os.getenv("REVENUE_CAT_WEBHOOK_TOKEN")
CACHE_DOCUMENT_URL_TEMPLATE = os.getenv("CACHE_DOCUMENT_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/document/{doc_id}")
CACHE_IMAGE_URL_TEMPLATE = os.getenv("CACHE_IMAGE_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/image/{doc_id}")
CACHE_VIDEO_URL_TEMPLATE = os.getenv("CACHE_VIDEO_URL_TEMPLATE", "https://api.academiai.org/api/v1/tools/retrieve_video/{video_id}")


SEARCHX_HOST = os.getenv("SEARCHX_HOST", "http://localhost:8090")
APP_DOMAIN = os.getenv("APP_DOMAIN", "https://api.academiai.org")
GET_CV_IMAGES_ENDPOINT = APP_DOMAIN + "/api/v1/cv_maker/get_image/{name}"
MERMAID_SERVER_URL = os.getenv("MERMAID_SERVER_URL")


#GPTS
GPT_API_KEY = os.getenv("GPT_API_KEY", "ZAIGHAMNETTTTTTTT!!1234!!CHUTIKRRRR!!!")
CYCLE_TLS_SERVER_URL = os.getenv("CYCLE_TLS_SERVER_URL", "http://localhost:3000/fetch")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "zain0694-20")
HTTP_PROXY_URL = os.getenv("HTTP_PROXY_URL")


RAPID_API_PROXY_SECRET = os.getenv("RAPID_API_PROXY_SECRET", "4510d130-4405-11ef-aa50-39a12d6a1df8")
RAPID_API_PROXY_SECRET_WHISPER = os.getenv("RAPID_API_PROXY_SECRET_WHISPER", "7d2ba360-7c04-11ef-be1c-f9db4fa6a10f")
