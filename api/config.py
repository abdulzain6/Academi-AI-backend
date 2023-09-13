import os
from dotenv import load_dotenv

load_dotenv()

UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY", None)
UNSTRUCTURED_URL = os.getenv("UNSTRUCTURED_URL", "http://localhost:8080/general/v0/general")
OPENAI_APIKEY = os.getenv("OPENAI_APIKEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_URL = os.getenv("QDRANT_URL", "localhost")
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "study-app")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
QUIZ_MAX_API_CALLS = os.getenv("QUIZ_MAX_API_CALLS", 5)