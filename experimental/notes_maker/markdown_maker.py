import tempfile
import pypandoc
import os
import io
from pydantic import BaseModel
from docx import Document
from docx.shared import RGBColor
from .base import NotesMaker

class MarkdownData(BaseModel):
    content: str

class MarkdownNotesMaker(NotesMaker):
    def make_notes(self, data: MarkdownData, context: None = None):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(markdown_data.content, 'docx', format='md', outputfile=temp_file.name)
            temp_file_path = temp_file.name

        # Open the generated DOCX file with python-docx
        doc = Document(temp_file_path)

        # Iterate through paragraphs and set text color to black
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)  # RGB values for black

        # Save the modified DOCX content to a BytesIO object
        file_obj = io.BytesIO()
        doc.save(file_obj)
        file_obj.seek(0)  # Reset the file pointer to the beginning of the file

        os.unlink(temp_file_path)  # Delete the temporary file

        return file_obj


if __name__ == '__main__':
    markdown_content = """
# Heading 1
    
    Some text under heading 1.
    
## Heading 2
    
    Some text under heading 2.
    """
    markdown_data = MarkdownData(content=markdown_content)
    notes_maker = MarkdownNotesMaker()
    file_object = notes_maker.make_notes(markdown_data)
    with open("output.docx", "wb") as file:
        file.write(file_object.read())