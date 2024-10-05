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
    
    def generate_speech(self, input_text: str, model: str = "tts-1", voice: str = "alloy") -> io.BytesIO:
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
                         output_path: str, extra_duration: float = 3, transition_duration: float = 2):
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
        final_clip.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")

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



if __name__ == "__main__":
    placeholders = [
        {'placeholders': [{'placeholder_name': 'TOPIC', 'placeholder_data': 'Thermodynamics.', 'description': 'The topic of the presentation', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'PRESENTOR_NAME', 'placeholder_data': 'John Doe.', 'description': 'The name of the presentor', 'is_image': False, 'image_width': None, 'image_height': None}],
         'page_number': 1,
         'slide_detail': 'Thermodynamics',
         'slide_type': 'TITLE_SLIDE'
        }, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Introduction to Thermodynamics.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SECTION_CONTENT', 'placeholder_data': '- Study of energy and heat transfer\n- Focuses on energy conversion\n- Key principles include systems and surroundings\n- Involves laws governing energy interactions\n- Essential for understanding physical phenomena\n- Applications in engineering, chemistry, and physics', 'description': 'The content for the section.', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 2, 'slide_detail': 'Introduction to Thermodynamics', 'slide_type': 'CONTENT_SLIDE'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Laws of Thermodynamics.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'First Law of Thermodynamics.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Energy cannot be created or destroyed\n- Total energy of an isolated system is constant\n- Internal energy change equals heat added minus work done', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO', 'placeholder_data': 'Second Law of Thermodynamics.', 'description': 'The name for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- Entropy of an isolated system always increases\n- Heat cannot spontaneously flow from cold to hot\n- Energy transformations are not 100% efficient', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 3, 'slide_detail': 'Laws of Thermodynamics', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Laws of Thermodynamics (contd.).', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'Second Law of Thermodynamics.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Energy transfer creates entropy\n- Heat flows from hot to cold\n- Efficiency limits in energy conversion', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- Absolute zero as a limit\n- Entropy approaches constant value\n- No energy can be extracted at absolute zero', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 4, 'slide_detail': 'Laws of Thermodynamics (contd.)', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Thermodynamic Processes.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SECTION_CONTENT', 'placeholder_data': '- Definition: Transformation of energy\n- Importance: Foundations of thermodynamics\n- Types: Isobaric, Isochoric, Isothermal, Adiabatic\n- Characteristics: Heat transfer, Work done, System behavior\n- Applications: Engineering, Physics, Chemistry', 'description': 'The content for the section.', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 5, 'slide_detail': 'Thermodynamic Processes', 'slide_type': 'CONTENT_SLIDE'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Types of Thermodynamic Processes.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'Isothermal Processes.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Constant temperature\n- Heat is exchanged\n- Common in gas expansion', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO', 'placeholder_data': 'Adiabatic Processes.', 'description': 'The name for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- No heat exchange\n- Temperature changes\n- Rapid processes', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 6, 'slide_detail': 'Types of Thermodynamic Processes', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Types of Thermodynamic Processes (contd.).', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'Isothermal Process.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Constant temperature\n- Heat exchange occurs\n- Example: Melting of ice', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO', 'placeholder_data': 'Adiabatic Process.', 'description': 'The name for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- No heat exchange\n- Temperature changes due to work done\n- Example: Rapid compression of gas', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 7, 'slide_detail': 'Types of Thermodynamic Processes (contd.)', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Thermodynamic Cycles.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SECTION_CONTENT', 'placeholder_data': '- Defined as a series of processes\n- Return to initial state\n- Key types: Carnot, Otto, Diesel\n- Efficiency calculated using work and heat\n- Applications in engines and refrigeration\n- Important for energy conversion studies\n- Involves heat addition and rejection', 'description': 'The content for the section.', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 8, 'slide_detail': 'Thermodynamic Cycles', 'slide_type': 'CONTENT_SLIDE'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Examples of Thermodynamic Cycles.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'Carnot Cycle.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Idealized thermodynamic cycle\n- Consists of two isothermal and two adiabatic processes\n- Maximum efficiency between two temperature reservoirs\n- Used as a standard for real cycles', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO', 'placeholder_data': 'Otto Cycle.', 'description': 'The name for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- Used in gasoline engines\n- Consists of two adiabatic and two isochoric processes\n- Converts heat into work\n- Efficiency depends on compression ratio', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 9, 'slide_detail': 'Examples of Thermodynamic Cycles', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Applications of Thermodynamics.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SECTION_CONTENT', 'placeholder_data': '- Energy conversion systems\n- Refrigeration and air conditioning\n- Heat engines and power plants\n- Chemical reactions and process engineering\n- Material science and phase transitions\n- Environmental impact assessments\n- Biomedical applications\n- Renewable energy technologies', 'description': 'The content for the section.', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 10, 'slide_detail': 'Applications of Thermodynamics', 'slide_type': 'CONTENT_SLIDE'}, {'placeholders': [{'placeholder_name': 'SECTION', 'placeholder_data': 'Real-World Applications.', 'description': 'The name of the section', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE', 'placeholder_data': 'Energy Generation.', 'description': 'The name of the subsection number one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_ONE_CONTENT', 'placeholder_data': '- Power plants utilize thermodynamics for electricity\n- Steam turbines convert heat energy into work\n- Solar panels harness solar energy efficiently', 'description': 'The content for subsection numner one', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO', 'placeholder_data': 'Refrigeration and Air Conditioning.', 'description': 'The name for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}, {'placeholder_name': 'SUBSECTION_TWO_CONTENT', 'placeholder_data': '- Refrigerators use thermodynamic cycles to cool\n- Air conditioning systems regulate indoor temperature\n- Heat pumps transfer thermal energy effectively', 'description': 'The content for subsection number two', 'is_image': False, 'image_width': None, 'image_height': None}], 'page_number': 11, 'slide_detail': 'Real-World Applications', 'slide_type': 'MULTI_COLUMN'}, {'placeholders': [], 'page_number': 12, 'slide_detail': 'Thank You!', 'slide_type': 'THANKYOU_SLIDE'}]
    
    
    input = LectureMakerInput(
        topic="Thermodynamics",
        instructions="Explain all subtopics",
        presentation_path="/home/zain/Downloads/tmpt8bzvd2t.pptx",
        slides_text=[
            Slide(
                slide_type=slide["slide_type"],
                slide_subtopic=slide["slide_detail"],
                slide_text="\n".join([f'{data["placeholder_name"]} : {data["placeholder_data"]}' for data in slide["placeholders"]])
            ) for slide in placeholders]
    )
    from langchain_openai import ChatOpenAI
    generator = LectureGenerator(ChatOpenAI(model="gpt-4o-mini"))
    lecture = generator.run(lecture_input=input)
    print(" ".join([slide.script for slide in lecture.slide_scripts]))
