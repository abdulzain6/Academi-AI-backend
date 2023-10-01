import json
import os
from typing import Dict
from dotenv import load_dotenv

load_dotenv()


def get_dict_from_env_var(env_var_name: str, default: Dict = None) -> Dict:
    env_val = os.environ.get(env_var_name)
    return json.loads(env_val) if env_val is not None else default



UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", None)
UNSTRUCTURED_URL = os.getenv("UNSTRUCTURED_URL", "http://localhost:8080/general/v0/general")
OPENAI_APIKEY = os.getenv("OPENAI_APIKEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
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
REQUEST_TIMEOUT = os.getenv("REQUEST_TIMEOUT", 250)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:10001")
CACHE_TTL = os.getenv("CACHE_TTL", 5 * 24 * 60 * 60)
DEFAULT_POINTS = os.getenv("DEFAULT_POINTS", 10)
FEATURE_PRICING = get_dict_from_env_var(
    "FEATURE_PRICING", 
    {
        "QUIZ" : 3,
        "CHAT" : 1,
        "OCR" : 1,
        "PRESENTATION" : 4,
        "FLASHCARDS" : 2,
        "WRITER" : 2
    }
)
