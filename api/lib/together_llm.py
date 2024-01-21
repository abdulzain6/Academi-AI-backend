"""Wrapper around Together AI's Completion API."""
from typing import Dict

from langchain_core.pydantic_v1 import root_validator
from langchain_core.utils import get_from_dict_or_env
from langchain_community.chat_models.openai import ChatOpenAI
from langchain_together.version import __version__
import os


import logging
import os
from typing import (
    Dict,
    Union,
)

from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.pydantic_v1 import BaseModel, root_validator
from langchain_core.utils import (
    get_from_dict_or_env,
)

from langchain_community.adapters.openai import (
    convert_dict_to_message,
)



class Together(ChatOpenAI):
    openai_api_base: str = "https://api.together.xyz/v1"
    
    def _create_chat_result(self, response: Union[dict, BaseModel]) -> ChatResult:
        generations = []
        if not isinstance(response, dict):
            response = response.dict()
        for res in response["choices"]:
            message = convert_dict_to_message(res["message"])
            try:
                message.content = message.content.replace("\_", "_")
            except Exception as e:
                print(e)
            generation_info = dict(finish_reason=res.get("finish_reason"))
            if "logprobs" in res:
                generation_info["logprobs"] = res["logprobs"]
            gen = ChatGeneration(
                message=message,
                generation_info=generation_info,
            )
            generations.append(gen)
        token_usage = response.get("usage", {})
        llm_output = {
            "token_usage": token_usage,
            "model_name": self.model_name,
            "system_fingerprint": response.get("system_fingerprint", ""),
        }
        return ChatResult(generations=generations, llm_output=llm_output)


    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that api key and python package exists in environment."""
        if values["n"] < 1:
            raise ValueError("n must be at least 1.")
        if values["n"] > 1 and values["streaming"]:
            raise ValueError("n must be 1 when streaming.")

        values["openai_api_key"] = get_from_dict_or_env(
            values, "openai_api_key", "TOGETHER_API_KEY"
        )
        values["openai_api_base"] = values["openai_api_base"] or os.getenv(
            "OPENAI_API_BASE"
        )
        try:
            import openai

        except ImportError:
            raise ImportError(
                "Could not import openai python package. "
                "Please install it with `pip install openai`."
            )

        client_params = {
            "api_key": values["openai_api_key"],
            "organization": values["openai_organization"],
            "base_url": values["openai_api_base"],
            "timeout": values["request_timeout"],
            "max_retries": values["max_retries"],
            "default_headers": values["default_headers"],
            "default_query": values["default_query"],
            "http_client": values["http_client"],
        }
        if not values.get("client"):
            values["client"] = openai.OpenAI(**client_params).chat.completions
        if not values.get("async_client"):
            values["async_client"] = openai.AsyncOpenAI(
                **client_params
            ).chat.completions
            
        return values