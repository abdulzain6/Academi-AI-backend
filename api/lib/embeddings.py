from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, cast
import warnings
from langchain_community.embeddings.openai import OpenAIEmbeddings, embed_with_retry

import os
import warnings
from typing import (
    Dict,
    List,
    Optional,
    cast,
)


from langchain_core.pydantic_v1 import root_validator
from langchain_core.utils import get_from_dict_or_env
from langchain_community.utils.openai import is_openai_v1

class TogetherEmbeddingsParallel(OpenAIEmbeddings):    
    openai_api_base: Optional[str] ="https://api.together.xyz/v1"
    model: str = "togethercomputer/m2-bert-80M-8k-retrieval"

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that api key and python package exists in environment."""
        values["openai_api_key"] = get_from_dict_or_env(
            values, "openai_api_key", "TOGETHER_API_KEY"
        )
        values["openai_api_base"] = values["openai_api_base"] or os.getenv(
            "OPENAI_API_BASE"
        )
        values["openai_api_type"] = get_from_dict_or_env(
            values,
            "openai_api_type",
            "OPENAI_API_TYPE",
            default="",
        )
        values["openai_proxy"] = get_from_dict_or_env(
            values,
            "openai_proxy",
            "OPENAI_PROXY",
            default="",
        )
        if values["openai_api_type"] in ("azure", "azure_ad", "azuread"):
            default_api_version = "2023-05-15"
            # Azure OpenAI embedding models allow a maximum of 16 texts
            # at a time in each batch
            # See: https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#embeddings
            values["chunk_size"] = min(values["chunk_size"], 16)
        else:
            default_api_version = ""
        values["openai_api_version"] = get_from_dict_or_env(
            values,
            "openai_api_version",
            "OPENAI_API_VERSION",
            default=default_api_version,
        )
        # Check OPENAI_ORGANIZATION for backwards compatibility.
        values["openai_organization"] = (
            values["openai_organization"]
            or os.getenv("OPENAI_ORG_ID")
            or os.getenv("OPENAI_ORGANIZATION")
        )
        try:
            import openai
        except ImportError:
            raise ImportError(
                "Could not import openai python package. "
                "Please install it with `pip install openai`."
            )
        else:
            if is_openai_v1():
                if values["openai_api_type"] in ("azure", "azure_ad", "azuread"):
                    warnings.warn(
                        "If you have openai>=1.0.0 installed and are using Azure, "
                        "please use the `AzureOpenAIEmbeddings` class."
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
                    values["client"] = openai.OpenAI(**client_params).embeddings
                if not values.get("async_client"):
                    values["async_client"] = openai.AsyncOpenAI(
                        **client_params
                    ).embeddings
            elif not values.get("client"):
                values["client"] = openai.Embedding
            else:
                pass
        return values
    
    def embed_query(self, text: str) -> List[float]:
        """Call out to OpenAI's embedding endpoint for embedding query text.

        Args:
            text: The text to embed.

        Returns:
            Embedding for the text.
        """
        return self.embed_documents([text])[0]
    
    def embed_documents(
        self, texts: List[str], chunk_size: Optional[int] = 0
    ) -> List[List[float]]:
        """Parallelize embedding of documents by sending two documents per request.

        Args:
            texts: The list of texts to embed.

        Returns:
            List of embeddings, one for each text.
        """
        def worker(text_group: List[str]) -> List[List[float]]:
            return self.embed_pair(text_group)

        # Grouping the texts into groups of 4
        group_size = 4
        text_groups = [texts[i:i + group_size] for i in range(0, len(texts), group_size)]

        # Use ThreadPoolExecutor to process groups in parallel
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, group) for group in text_groups]
            for future in as_completed(futures):
                results.extend(future.result())

        return results

    def embed_pair(self, text_pair: List[str]) -> List[List[float]]:
        """Embed a pair of documents.

        Args:
            text_pair: A pair of texts to embed.

        Returns:
            Embeddings for the pair.
        """
        embeddings = embed_with_retry(self, input=text_pair, model=self.model)
        return [r.embedding for r in embeddings.data]

