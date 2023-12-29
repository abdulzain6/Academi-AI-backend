import tempfile
import pypandoc
import os
import io
from pydantic import BaseModel
from docx import Document
from docx.shared import RGBColor
from langchain.chat_models.base import BaseChatModel
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chains import LLMChain
from .base import NotesMaker

class MarkdownData(BaseModel):
    content: str

class MarkdownNotesMaker(NotesMaker):
    def __init__(self, llm: BaseChatModel, **kwargs):
        self.llm = llm
        
    def make_notes_from_string(self, string: str, instructions: str) -> io.BytesIO:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """You are an AI designed to make cornell notes from text.
You must also follow the instructions given to you
Only answer from the notes given to you. No making things up
You must pick every minute detail.
You will return the notes in markdown
You must make super detailed and lenghty notes
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Use the following data to make the notes:
{data}
============

Follow the instructions below also:
============
{instructions}
============

The notes in markdown:"""
                ),
            ],
            input_variables=[
                "data",
                "instructions"
            ],
        )
        chain = LLMChain(prompt=prompt, llm=self.llm)
        notes = chain.run(data=string, instructions=instructions)
        return self.make_notes(data=MarkdownData(content=notes))
        
    def make_notes(self, data: MarkdownData, context: None = None):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
            pypandoc.convert_text(data.content, 'docx', format='md', outputfile=temp_file.name)
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
    from langchain.chat_models import ChatOpenAI
    
    note_maker = MarkdownNotesMaker(
        ChatOpenAI(temperature=0, openai_api_key="")
    )
    notes = note_maker.make_notes_from_string("""
World War II: An Epoch of Global Conflict and Change

The history of the 20th century is profoundly marked by the cataclysmic events of World War II, a global conflict that spanned six years, from 1939 to 1945. This war reshaped the world's geopolitical boundaries, altered global power dynamics, and set the stage for both the Cold War and the modern world order.

The war was principally a confrontation between two sets of powers: the Axis and the Allies. The Axis powers, chiefly comprised of Germany, Italy, and Japan, were driven by expansionist ambitions and authoritarian ideologies. Germany, under the rule of Adolf Hitler, played a pivotal role in the war's outbreak and progression. Hitler's aggressive policies and relentless pursuit of territorial expansion pushed Europe into a state of turmoil.

Japan's role in the Pacific theater was equally consequential. The Japanese attack on Pearl Harbor on December 7, 1941, marked a significant escalation of the war, drawing the United States into active combat. This surprise attack, aimed at neutralizing the American Pacific Fleet, stemmed from Japan's desire to dominate Southeast Asia without American intervention. The strategic motivations behind Japan's military actions in the Pacific, driven by economic and resource scarcities, illustrate the complex interplay of national interests that characterized the war.

The Allies, consisting of major powers like the United Kingdom, the United States, the Soviet Union, and France, among others, united to counter the aggression of the Axis powers. Their collaboration was marked by a shared commitment to defeating the forces of fascism and militarism.

Several key battles defined the trajectory of World War II. The Battle of Stalingrad was a turning point on the Eastern Front. The Soviet victory in this grueling battle marked the beginning of the decline for Nazi Germany. The Battle of Midway, a crucial naval conflict, signified a decisive shift in the Pacific, as American forces dealt a critical blow to the Japanese navy.

Another significant event was the Normandy Invasion, commonly known as D-Day, on June 6, 1944. This massive military operation, involving the landing of Allied forces on the beaches of Normandy, France, was a pivotal moment in liberating Western Europe from Nazi occupation.

The war's impact extended far beyond the battlefield. It brought about profound changes in political, social, and cultural realms. The Holocaust, a horrific genocide perpetrated by Nazi Germany, led to the systematic extermination of six million Jews, along with millions of others deemed undesirable by the Nazi regime. This atrocity highlighted the depths of human cruelty and the necessity for a robust international framework to prevent such crimes against humanity.

In the wake of the war, the United Nations was established, symbolizing the global community's aspiration for peace and cooperation. However, the world also witnessed the emergence of the Cold War, a period of geopolitical tension between the Soviet Union and the United States that lasted for decades.

As we delve deeper into the multifaceted narrative of World War II, it becomes evident that this conflict was not just a series of military engagements but also a clash of ideologies and civilizations. It challenged the notions of power, sovereignty, and human rights, leaving an indelible imprint on the course of human history.
""", "Dont miss anything")
    with open("file.docx", "wb") as fp:
        notes.seek(0)
        fp.write(notes.read())
