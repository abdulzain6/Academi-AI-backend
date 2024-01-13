from .four_column_maker import QuestionsKeywordsNotesMaker
from .markdown_maker import MarkdownNotesMaker
from .two_column_maker import QuestionsDetailsSummaryNotesMaker
from .base import NotesMaker
from langchain.chat_models.base import BaseChatModel
from typing import Type

note_maker_types: dict[str, Type[NotesMaker]] = {
    "Two Column Cornell": QuestionsDetailsSummaryNotesMaker,
    "Four Column Cornell": QuestionsKeywordsNotesMaker,
    "Text Notes": MarkdownNotesMaker,
}


def get_available_note_makers() -> list[str]:
    return list(note_maker_types.keys())

def get_available_note_makers_with_schema() -> list[dict]:
    note_maker_with_schema = []
    for k, w in note_maker_types.items():
        note_maker_with_schema.append(
            {"template_name" : k, "schema" : w.get_schema()}
        )
    return note_maker_with_schema

def make_notes_maker(
    maker_type: str, llm: BaseChatModel, template_path: str = None
) -> NotesMaker:
    if maker_type not in note_maker_types:
        raise ValueError("Note maker not available")
    note_maker = note_maker_types[maker_type]
    return note_maker(llm=llm, template_path=template_path)
