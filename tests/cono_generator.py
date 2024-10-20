import io
from openai import OpenAI
from langchain.pydantic_v1 import BaseModel, Field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from typing import List
from pydub import AudioSegment
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI



class Voice(str, Enum):
    alloy = "alloy"
    echo = "echo"
    fable = "fable"
    onyx = "onyx"
    nova = "nova"
    shimmer = "shimmer"

class ConversationPart(BaseModel):
    speaker: Voice = Field(..., description="The voice representing the speaker", example="alloy")
    text: str = Field(..., description="The actual content of the dialogue", example="Hello, how are you?")
    delay: float = Field(1.0, description="Silence delay in seconds before the next part", example=1.0)

class Conversation(BaseModel):
    parts: List[ConversationPart] = Field(
        ..., 
        description="List of conversation parts"
    )


class SpeechGenerator:
    def __init__(self, llm: BaseChatModel, model: str = "tts-1") -> None:
        self.llm = llm
        self.model = model

    def generate_speech(self, input_text: str, voice: Voice, model: str = "tts-1") -> io.BytesIO:
        """
        Generate speech audio using OpenAI's TTS model and return the audio as an in-memory file.
        """
        # Mocked response - replace this with your actual TTS logic
        client = OpenAI()
        response = client.audio.speech.create(
            model=model,
            voice=voice.value,
            input=input_text
        )
        
        audio_buffer = io.BytesIO(response.read())            
        audio_buffer.seek(0)
        
        return audio_buffer

    def generate_speech_for_conversation(self, conversation: Conversation) -> AudioSegment:
        """
        Generate speech for all parts of a conversation in parallel and stitch them together with delays.
        
        Args:
            conversation (Conversation): The conversation object containing parts.

        Returns:
            AudioSegment: The stitched audio of the entire conversation.
        """
        # Function to generate audio for each part
        def generate_audio(part: ConversationPart) -> AudioSegment:
            audio_file = self.generate_speech(part.text, part.speaker)
            return AudioSegment.from_file(audio_file, format="mp3")

        # Using ThreadPoolExecutor to generate speech in parallel for all parts
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(generate_audio, part) for part in conversation.parts]
            audio_parts = [future.result() for future in futures]

        # Initialize final audio with the first part
        final_audio = audio_parts[0]

        # Stitch parts together with appropriate delay
        for i in range(1, len(audio_parts)):
            delay_ms = int(conversation.parts[i-1].delay * 1000)  # Convert seconds to milliseconds
            silence = AudioSegment.silent(duration=delay_ms)
            final_audio += silence + audio_parts[i]

        return final_audio

    def generate_conversation(self, num_people: int, minutes: int, data: str) -> Conversation:
        system_message = """You are an AI designed to generate educational podcast like conversations.
You will generate conversations based on the text given to you.
The conversation will be between {num_people} people.
Make sure the voices of the people are consistent, do not mix voices.
Generate information filled conversations.
The conversation must be of around {minutes} minutes.
"""     
        messages = [
            ("system", system_message),
            ("human", "Generate a conversation fot the following piece of text data: {data}"),
        ]
        chat_prompt = ChatPromptTemplate.from_messages(messages)
        structured_llm = self.llm.with_structured_output(schema=Conversation)
        chain = chat_prompt | structured_llm
        return chain.invoke({"num_people": num_people, "minutes" : minutes, "data" : data})

    def run(self, num_people: int, minutes: int, data: str) -> AudioSegment:
        conversation = self.generate_conversation(num_people, minutes, data)
        return self.generate_speech_for_conversation(conversation)
        

if __name__ == "__main__":
    generator = SpeechGenerator(ChatOpenAI(model="gpt-4o-mini"), "tts-1-hd")
    audio = generator.run(
        2, 5, """The Impact of Technology on Modern Communication

In the 21st century, technology has transformed nearly every aspect of life, but perhaps its most profound effect has been on communication. With the advent of the internet, smartphones, and social media, the way humans interact has been revolutionized. Technology has bridged the geographical divides between people, enabling global connections that were unimaginable a few decades ago. However, alongside these advancements come concerns regarding privacy, the quality of interpersonal interactions, and the erosion of traditional forms of communication.

One of the most significant impacts of technology on communication is the speed at which information can now travel. In the past, a letter sent across the world could take weeks to reach its destination. Today, emails and instant messaging allow people to communicate with each other in real-time, regardless of physical distance. Platforms like WhatsApp, Telegram, and Facebook Messenger enable users to send text, voice messages, and multimedia within seconds. These tools have facilitated the growth of businesses, accelerated information exchange, and allowed people to stay in touch with loved ones regardless of their location.

Moreover, social media platforms such as Twitter, Instagram, and LinkedIn have changed the way individuals and organizations communicate publicly. Social media allows for the instantaneous sharing of news, opinions, and updates with vast audiences. It has also provided a platform for individuals to express their thoughts and ideas, giving rise to digital activism and the ability to influence public opinion on a global scale. For businesses, social media is an invaluable tool for marketing, customer service, and brand building, enabling direct communication with consumers in a way that was previously impossible.

Despite these benefits, the rise of technology in communication has also led to a number of concerns. One issue is the growing dependency on digital communication, which can sometimes come at the expense of face-to-face interactions. Many people today prefer texting or emailing over meeting in person or making a phone call, which can diminish the quality of relationships and the depth of human connection. Non-verbal cues, such as body language and tone of voice, are often lost in text-based communication, making it harder to interpret the true meaning behind a message.

Additionally, privacy concerns have arisen as a result of technology's pervasiveness in communication. With the increase in data collection by tech companies, individuals' personal information is often vulnerable to breaches, hacks, and misuse. Social media platforms, for example, have been criticized for their handling of user data and the lack of transparency in how personal information is shared or sold to third parties. As technology continues to advance, there is a growing need for regulations and ethical standards to protect individuals' privacy and security online.

In conclusion, while technology has undeniably improved the efficiency and reach of communication, it has also introduced new challenges. The ease with which we can now communicate with anyone, anywhere, comes with trade-offs in terms of privacy, the quality of interpersonal interactions, and the potential for social disconnection. As society continues to integrate technology into daily life, it is important to strike a balance between leveraging its benefits and addressing the challenges it presents.

""")
    audio.export("two_speakers_conversation_output.mp3", format="mp3")
