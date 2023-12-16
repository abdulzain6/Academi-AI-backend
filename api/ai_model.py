from pydantic import BaseModel
from langchain.chat_models.base import BaseChatModel
from langchain.llms.base import BaseLLM

class AIModel(BaseModel):
    regular_model: object
    regular_args: dict
    regular_binds: dict
    premium_model: object
    premium_args: dict
    premium_binds: dict