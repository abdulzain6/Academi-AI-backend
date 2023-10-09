from abc import ABC, abstractmethod

class NotesMaker(ABC):
    @abstractmethod
    def make_notes(self, data, context):
        pass