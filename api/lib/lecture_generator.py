from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import tempfile
import uuid
from langchain.pydantic_v1 import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
import numpy as np
from openai import OpenAI
from pdf2image import convert_from_path
from io import BytesIO
from typing import List, Tuple
from moviepy.editor import *
from PIL import Image
import io
import os
import subprocess
import logging
import multiprocessing


class Slide(BaseModel):
    slide_text: str
    slide_subtopic: str
    slide_type: str

class LectureMakerInput(BaseModel):
    topic: str
    instructions: str
    presentation_path: str
    slides_text: list[Slide]
    minutes: int = 10
    language: str = "English"
    

class SlideScript(BaseModel):
    script: str = Field(description="The script for the slide.")
    slide_number: int
    
class LectureScript(BaseModel):
    slide_scripts: list[SlideScript]
    
class LectureGenerator:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
    
    def generate_lecture(self, lecture_input: LectureMakerInput) -> LectureScript:
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    """
You are an AI designed to generate lecture scripts for students to listen to.
You are to generate a lecture script on the topic '{topic}' in {language}.
You will split the script by slide numbers. 
Each slide will have its own script but you must make sure they are connected and build upon previous slides.
Follow the instructions below:
==========
 1. Cover all subtopics for the topic
 2. Use easy language for students to understand.
 {instructions}
==========
The lecture length will be of {minutes} minutes. Try to stay in that limit.
Keep the slide text and type in mind!
"""
                ),
                HumanMessagePromptTemplate.from_template(
                    """
Here is the text from the slides, tailor your script according to the text.
==========
{slides}
==========
"""
                ),
            ],
            input_variables=[
                "topic",
                "language",
                "instructions",
                "minutes",
                "slides"
            ],
        )
        slide_text = ""
        for i, slide in enumerate(lecture_input.slides_text):
            slide_text += f"""

Slide number: {i} | Slide is about: {slide.slide_subtopic} | |Slide Type: {slide.slide_type}
Slide Text:
==============
{slide.slide_text}
==============

"""
        messages = prompt.format_messages(
            topic=lecture_input.topic,
            language=lecture_input.language,
            instructions=lecture_input.instructions,
            minutes=lecture_input.minutes,
            slides=slide_text
        )
        structured_llm = self.llm.with_structured_output(schema=LectureScript)
        return structured_llm.invoke(messages)
    
    def generate_speech(self, input_text: str, model: str = "tts-1", voice: str = "onyx") -> io.BytesIO:
        """
        Generate speech audio using OpenAI's TTS model and return the audio as an in-memory file.

        Args:
            input_text (str): The text to convert into speech.
            model (str): The TTS model to use. Default is "tts-1".
            voice (str): The voice model to use. Default is "alloy".

        Returns:
            io.BytesIO: The in-memory audio file in MP3 format.
        """

        client = OpenAI()
        
        try:
            response = client.audio.speech.create(
                model=model,
                voice=voice,
                input=input_text
            )
            
            # Create an in-memory bytes buffer to store the audio file
            audio_buffer = io.BytesIO(response.read())            
            
            # Reset the buffer position to the beginning after writing
            audio_buffer.seek(0)
            
            return audio_buffer

        except Exception as e:
            raise RuntimeError(f"Failed to generate speech: {str(e)}")

    def create_slideshow(self, images: List[io.BytesIO], audios: List[Tuple[int, io.BytesIO]], 
                         output_path: str, extra_duration: float = 2.5, transition_duration: float = 2):
        """
        Create a slideshow video with synchronized audio and transitions.

        Args:
            images (List[io.BytesIO]): List of image buffers.
            audios (List[Tuple[int, io.BytesIO]]): List of tuples containing slide number and audio buffer.
            output_path (str): Path to save the output video.
            extra_duration (float): Extra duration to show slide after audio ends. Default is 4 seconds.
            transition_duration (float): Duration of transition between slides. Default is 2 seconds.
        """
        clips = []
        audio_clips = []
        total_duration = 0

        for i, (image_buffer, (slide_number, audio_buffer)) in enumerate(zip(images, audios)):
            # Convert BytesIO to numpy array
            image = Image.open(image_buffer)
            img_array = np.array(image)

            # Create a temporary file for the audio
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio_file:
                temp_audio_file.write(audio_buffer.getvalue())
                temp_audio_file_path = temp_audio_file.name

            # Load audio
            audio = AudioFileClip(temp_audio_file_path)
            
            # Calculate slide duration
            slide_duration = audio.duration + extra_duration

            # Create image clip
            img_clip = ImageClip(img_array).set_duration(slide_duration)

            # Add fade in/out effect
            img_clip = img_clip.fx(vfx.fadeout, duration=transition_duration/2)
            if i > 0:
                img_clip = img_clip.fx(vfx.fadein, duration=transition_duration/2)

            # Set the start time of the clip
            img_clip = img_clip.set_start(total_duration)

            # Add transition pause to audio
            pause = AudioClip(lambda t: 0, duration=transition_duration).set_fps(44100)
            audio_with_pause = concatenate_audioclips([audio, pause])

            # Set the start time of the audio
            audio_with_pause = audio_with_pause.set_start(total_duration)

            clips.append(img_clip)
            audio_clips.append(audio_with_pause)

            # Update total duration
            total_duration += slide_duration

            # Clean up the temporary audio file
            os.unlink(temp_audio_file_path)

        # Concatenate all clips
        final_clip = CompositeVideoClip(clips, size=clips[0].size)
        final_audio = CompositeAudioClip(audio_clips)

        # Set the audio of the final clip
        final_clip = final_clip.set_audio(final_audio)

        # Set the duration of the final clip
        final_clip = final_clip.set_duration(total_duration)

        # Write the result to a file
        final_clip.write_videofile(output_path, fps=7, codec="libx264", audio_codec="aac", threads=multiprocessing.cpu_count())



    def run(self, lecture_input: LectureMakerInput) -> str:
        script = self.generate_lecture(lecture_input)
        images = self.convert_all_slides_to_images(lecture_input.presentation_path)
        audios = self.generate_lecture_speech(script)

        output_path = "lecture_slideshow.mp4"
        self.create_slideshow(images, audios, output_path)

        return output_path

    def convert_all_slides_to_images(self, ppt_path: str) -> List[BytesIO]:
        """
        Converts all slides of a PPTX presentation to images using LibreOffice for conversion to PDF
        and pdf2image for converting each page of the PDF to an image. Ensures unique temporary files for
        each conversion and cleans up afterward, with robust error handling.
        
        Args:
            pptx_path (BytesIO): The PPTX file content as bytes.
            
        Returns:
            List[BytesIO]: A list of BytesIO objects, each containing an image of a slide.
        """
        # Initialize paths
        temp_pdf_path = None
        image_list = []
        
        try:
            new_name = os.path.join("/tmp", f"{uuid.uuid4()}.pptx")
            shutil.copyfile(ppt_path, new_name)

            # Convert the PPTX to a PDF using LibreOffice
            subprocess.run(['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', "/tmp", new_name], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            temp_pdf_path = f"/tmp/{os.path.basename(new_name).replace('pptx', 'pdf')}"
            
            print(f"Pdf written to {temp_pdf_path}")
            # Verify PDF was created before proceeding
            if not os.path.exists(temp_pdf_path):
                logging.error("PDF conversion failed or the PDF file was not created.")
                return []
            
            # Convert all pages of the PDF to images
            print("Converting all slides to images")
            images = convert_from_path(temp_pdf_path, thread_count=4)
            
            if images:
                # Convert each image to a BytesIO object and store it in a list
                for image in images:
                    image_bytes = BytesIO()
                    image.save(image_bytes, format='JPEG')
                    image_bytes.seek(0)
                    image_list.append(image_bytes)
            else:
                logging.error("No slides found in the PDF.")
                return []
            
            return image_list
        
        except Exception as e:
            import traceback
            logging.error(f"Error during slide to image conversion: {traceback.format_exception(e)}")
            return []
        
    def generate_lecture_speech(self, lecture_script: LectureScript, max_workers: int = 5) -> List[tuple[int, io.BytesIO]]:
        """
        Generate speech for all slides in the lecture script in parallel.

        Args:
            lecture_script (LectureScript): The lecture script containing all slide scripts.
            max_workers (int): The maximum number of worker threads to use. Default is 5.

        Returns:
            List[tuple[int, io.BytesIO]]: A list of tuples containing the slide number and its corresponding audio buffer.
        """
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_slide = {
                executor.submit(self.generate_speech, slide.script): slide.slide_number
                for slide in lecture_script.slide_scripts
            }

            results = []
            for future in as_completed(future_to_slide):
                slide_number = future_to_slide[future]
                try:
                    audio_buffer = future.result()
                    results.append((slide_number, audio_buffer))
                except Exception as e:
                    print(f"Speech generation failed for slide {slide_number}: {str(e)}")

        return sorted(results, key=lambda x: x[0])  # Sort by slide number



from ..firebase import *
from ..globals import temp_knowledge_manager, template_manager, knowledge_manager
from .presentation_maker.presentation_maker import PresentationMaker, PresentationInput
from .presentation_maker.image_gen import PexelsImageSearch
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
topic = "Thermodynamics"
instructions = "Explain all subtopics"
presentation_maker = PresentationMaker(
    template_manager,
    temp_knowledge_manager,
    llm,
    pexel_image_gen_cls=PexelsImageSearch,
    image_gen_args={"image_cache_dir": "/tmp/.image_cache"},
    vectorstore=knowledge_manager,
)
presentation_path, placeholders = presentation_maker.make_presentation(
    PresentationInput(
        topic=topic,
        instructions=instructions,
        number_of_pages=12,
        negative_prompt="",
        collection_name=None,
        files=None,
        user_id=None
    )
)

input = LectureMakerInput(
    topic=topic,
    instructions=instructions,
    presentation_path=presentation_path,
    language="Hinglish",
    slides_text=[
        Slide(
            slide_type=slide["slide_type"],
            slide_subtopic=slide["slide_detail"],
            slide_text="\n".join([f'{data["placeholder_name"]} : {data["placeholder_data"]}' for data in slide["placeholders"]])
        ) for slide in placeholders]
)
generator = LectureGenerator(llm)
lecture = generator.run(lecture_input=input)
print(lecture)
