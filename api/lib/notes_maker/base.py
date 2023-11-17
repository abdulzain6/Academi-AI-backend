from abc import ABC, abstractmethod
import io

class NotesMaker(ABC):
    @abstractmethod
    def make_notes(self, data, context):
        pass
    
    @abstractmethod
    def make_notes_from_string(self, string: str, instructions: str) -> io.BytesIO:
        pass