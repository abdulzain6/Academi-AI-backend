from abc import ABC, abstractmethod
from langchain.chat_models.base import BaseChatModel
import io

class NotesMaker(ABC):
    @abstractmethod
    def __init__(self, llm: BaseChatModel, **kwargs):
        ...
        
    @abstractmethod
    def make_notes(self, data, context):
        pass
    
    @abstractmethod
    def make_notes_from_string(self, string: str, instructions: str) -> io.BytesIO:
        pass