from pydantic import BaseModel
from langchain.chat_models.base import BaseChatModel
from langchain.llms.base import BaseLLM

class AIModel(BaseModel):
    regular_model: object
    premium_model: object
