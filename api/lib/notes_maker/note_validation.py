import logging
from ...globals import knowledge_manager_notes, notes_db
from langchain.schema import Document



def is_note_worthy(note: str):
    doc_and_scores = knowledge_manager_notes.query_data_with_score(note, 1, {})
    for doc, distance in doc_and_scores:
        logging.info(f"Distance: {distance}")
        if distance < 0.15:
            return False
    return True


def add_note(note: str, note_id: str):
    knowledge_manager_notes.injest_data(
        [
            Document(
                page_content=note,
                metadata={"note_id": note_id},
            )
        ],
        check_length=False,
    )
