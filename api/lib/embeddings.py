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
from langchain_together.embeddings import TogetherEmbeddings

class TogetherEmbeddingsParallel(TogetherEmbeddings):    
    model: str = "togethercomputer/m2-bert-80M-8k-retrieval"
    
