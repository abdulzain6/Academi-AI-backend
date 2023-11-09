import tiktoken
from langchain.text_splitter import TokenTextSplitter
import random

def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens



def select_random_chunks(text: str, chunk_size: int, total_length: int) -> str:
    texts = TokenTextSplitter(chunk_size=chunk_size).split_text(text)
    random.shuffle(texts)
    selected_text = ''
    for chunk in texts:
        if num_tokens_from_string(selected_text) + num_tokens_from_string(chunk) <= total_length:
            selected_text += chunk
        else:
            break
            
    return selected_text