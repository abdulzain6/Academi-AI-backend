import io
import logging
import os
import tempfile
import uuid
import pypandoc
from docx import Document
from docx.shared import RGBColor
import requests
import vl_convert as vlc
from typing import List, Dict, Union, Optional, IO
from scholarly import scholarly
from langchain.tools.base import BaseTool
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)
from api.lib.database.files import FileModel
from api.lib.presentation_maker.presentation_maker import (
    PresentationMaker,
    PresentationInput,
)
from api.lib.writer import Writer, ContentInput
from api.lib.uml_diagram_maker import AIPlantUMLGenerator
from langchain.pydantic_v1 import BaseModel
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from PIL import Image
from langchain_community.utilities.requests import TextRequestsWrapper
from bs4 import BeautifulSoup
from langchain_community.utilities.searx_search import SearxSearchWrapper
from api.lib.utils import convert_youtube_url_to_standard, format_url
from api.routers.utils import image_to_pdf_in_memory
from api.lib.cv_maker.cv_maker import CVMaker
from api.lib.notes_maker import NotesMaker
from graphviz import Source



def _clean_url(url: str) -> str:
    """Strips quotes from the url."""
    return url.strip("\"'")

def strip_html(html_content: str, max_length: int = 1000) -> str:
    """Strip HTML tags and limit response length."""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_length]


class BaseRequestsTool(BaseModel):
    """Base class for requests tools."""

    requests_wrapper: TextRequestsWrapper

class RequestsGetTool(BaseRequestsTool, BaseTool):
    """Tool for making a GET request to an API endpoint."""

    name: str = "requests_get"
    description: str = "A portal to the internet. Use this when you need to get specific content from a website. Input should be a  url (i.e. https://www.google.com). The output will be the text response of the GET request."

    def _run(
        self, url: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Run the tool."""
        response = self.requests_wrapper.get(_clean_url(url))
        return strip_html(response, max_length=5000)  # Set max length as needed

    async def _arun(
        self,
        url: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        """Run the tool asynchronously."""
        response = await self.requests_wrapper.aget(_clean_url(url))
        return strip_html(response, max_length=5000)

class MakePresentationInput(PresentationInput):
    template_name: Optional[str] = ""

class MarkdownToDocConverter(BaseTool):
    """Tool that converts Markdown text to a PDF file in memory."""

    name: str = "make_doc_notes_or_make_table"
    description: str = (
        "A tool to give the user a docx with the content of your choice"
        "Also Can be used to give the user a timetable a routine or notes"
        "Input should be the content of the docx in Markdown (Important!)."
    )
    cache_manager: object
    url_template: str

    def _run(
        self,
        content: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        *args,
        **kwargs,
    ) -> Union[IO[bytes], str]:
        """Convert Markdown text to a PDF file."""
        try:
            # Generate a unique ID for the document
            doc_id = f"{str(uuid.uuid4())}.docx"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as temp_file:
                pypandoc.convert_text(content, 'docx', format='md', outputfile=temp_file.name, sandbox=True)
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

            document_url = self.url_template.format(doc_id=doc_id)
            self.cache_manager.set(key=doc_id, value=file_obj.read(), ttl=18000, suppress=False)
            return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"

        except Exception as e:
            return f"An error occurred: {e}"

class ScholarlySearchRun(BaseTool):
    """Tool that queries the scholarly search API."""

    name: str = "google_scholar"
    description: str = (
        "A wrapper around google search "
        "Useful for finding scholarly articles. "
        "Use only if needed"
    )

    def _run(
        self,
        query: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        *args,
        **kwargs,
    ) -> List[Dict[str, Union[str, Optional[str]]]]:
        """Use the tool."""
        search_query = scholarly.search_pubs(query)
        results: List[Dict[str, Union[str, Optional[str]]]] = []
        count = 0
        while count < 6:
            try:
                paper = next(search_query)
                title = paper["bib"].get("title", "N/A")
                authors = paper["bib"].get("author", "N/A")
                year = paper["bib"].get("pub_year", "N/A")
                pdf_url = paper.get("eprint_url", "N/A")

                results.append(
                    {
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "url": pdf_url,  # Prioritize eprint_url for PDF
                    }
                )

                count += 1
            except StopIteration:
                # No more papers to process
                break
            except Exception as e:
                return f"An error occurred: {e}"

        return results

class SearchTool(BaseTool):
    seachx_wrapper: SearxSearchWrapper

    name: str = "search_web"
    description: str = "A portal to the internet. Use this when you need to use a search engine to search for things"

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Run the tool."""
        response = self.seachx_wrapper.results(
            query=query, num_results=self.seachx_wrapper.k
        )
        return response

class SearchImage(BaseTool):
    name: str = "search_image"
    description: str = "Used to search image from the internet, can be used to look for search aids"
    instance_url: str = 'http://localhost:8090'
    limit: int = 1
    
    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        params = {
            'q': query,
            'categories': 'images',
            'format': 'json'
        }
        
        response = requests.get(f"{self.instance_url}/search", params=params)
        if response.status_code == 200:
            results = response.json()['results']
            return f"Links: {[result['img_src'] for result in results][:self.limit]} User wont recieve images unless you read links out explicitly for them"  # Limit the results here
        else:
            return "No image found"

    
def create_link_file(
    user_id: str,
    subject_name: str,
    filename: str,
    youtube_link: str = None,
    web_link: str = None,
):
    from api.dependencies import can_add_more_data
    from ..globals import knowledge_manager, file_manager, collection_manager

    try:
        can_add_more_data(user_id, subject_name, collection_check=False)
    except Exception as e:
        return f"Error: {e}"
    
    
    logging.info(f"Create linkfile request from {user_id}")
    youtube_link = convert_youtube_url_to_standard(
        format_url(youtube_link)
    )
    web_link = format_url(web_link)
    logging.info(f"Fixing url for {user_id}")


    collection = collection_manager.get_collection_by_name_and_user(
        subject_name, user_id
    )
    logging.info(f"Collection: {collection}")
    if not collection:
        logging.error(f"Collection does not exist. {user_id}")
        raise ValueError("Subject does not exist")

    if not youtube_link and not web_link:
        raise ValueError(
            "Either weburl or youtube_link must be specified",
        )

    if youtube_link and web_link:
        raise ValueError(
            "Either weburl or youtube_link must be specified. Not both.",
        )

    if file_manager.file_exists(user_id, collection.collection_uid, filename):
        logging.error(f"File already exists {user_id}")
        raise ValueError(
            "File Already exists"
        )

    extension = ".yt" if youtube_link else ".html"

    try:
        logging.info("Started loading")
        contents, ids, file_bytes = knowledge_manager.load_web_youtube_link(
            metadata={"file": filename, "collection" : collection.name, "user" : user_id},
            youtube_link=youtube_link,
            web_url=web_link,
        )
    except Exception as e:
        import traceback
        logging.error(f"File not supported, Error: {traceback.format_exception(e)}")
        raise ValueError("Link has no data/ Invalid link") from e

    try:
        file_model = file_manager.add_file(
            FileModel(
                friendly_filename=filename,
                collection_name=subject_name,
                user_id=user_id,
                filename=filename,
                description="",
                file_content=contents,
                file_bytes=file_bytes,
                vector_ids=ids,
                filetype=extension,
            ),
        )
    except Exception as e:
        raise ValueError(str(e))
    
    logging.info(f"File created, File name: {file_model.filename}, Collection: {subject_name} {user_id}")
    return "Successfully created file! Now AI can make notes from it or read contents from it"

def make_cv_from_string(
    cv_maker: CVMaker, template_name: str, string: str, cache_manager, url_template: str
):
    doc_id = str(uuid.uuid4()) + ".pdf"
    with tempfile.NamedTemporaryFile(
        delete=True, suffix=".png", mode="w+b"
    ) as tmp_file:
        try:
            tmp_file_path = tmp_file.name
            output_file_name = os.path.basename(tmp_file_path)
            output_file_directory = os.path.dirname(tmp_file_path)
            _, missing = cv_maker.make_cv_from_string(
                template_name=template_name,
                string=string,
                output_file_path=output_file_directory,
                output_file_name=output_file_name,
            )
            if missing:
                missing_str = f"An average looking cv was made, There were missing fields: \n"  + '\n'.join(missing)  + "\nAsk the user to get better result more info is needed."
            else:
                missing_str = ""
            pdf_bytes = image_to_pdf_in_memory(tmp_file_path)
            cache_manager.set(key=doc_id, value=pdf_bytes, ttl=18000, suppress=False)
            document_url = url_template.format(doc_id=doc_id)
            return f"{missing_str}. Give the following link as it is to the user dont add sandbox prefix to it {document_url}. "
        except Exception as e:
            return f"There was an error : {e}"

def make_ppt(
    ppt_maker: PresentationMaker,
    ppt_input: MakePresentationInput,
    cache_manager,
    url_template: str,
):
    ppt_path, content = ppt_maker.make_presentation(
        template_name=ppt_input.template_name,
        presentation_input=PresentationInput(**ppt_input.model_dump()),
    )
    doc_id = str(uuid.uuid4()) + ".pptx"

    with open(ppt_path, "rb") as file:
        pdf_bytes = file.read()

    cache_manager.set(key=doc_id, value=pdf_bytes, ttl=18000, suppress=False)

    os.remove(ppt_path)
    document_url = url_template.format(doc_id=doc_id)
    return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"


def make_uml_diagram(
    uml_maker: AIPlantUMLGenerator,
    cache_manager,
    prompt: str,
    url_template: str,
):
    doc_id = str(uuid.uuid4()) + ".png"
    img_bytes = uml_maker.run(prompt=prompt)
    cache_manager.set(key=doc_id, value=img_bytes, ttl=18000, suppress=False)
    document_url = url_template.format(doc_id=doc_id)
    return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"

def make_vega_graph(
    vl_spec: str,
    cache_manager,
    url_template: str,
):
    # Generate a unique document identifier
    doc_id = str(uuid.uuid4()) + ".png"
    
    # Convert Vega-Lite specification to image bytes
    img_bytes = vega_lite_to_images(vl_spec=vl_spec)
    
    # If width and height are provided, resize the image using Pillow
    image = Image.open(io.BytesIO(img_bytes))
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    # Cache the image bytes using the provided cache manager
    cache_manager.set(key=doc_id, value=img_bytes, ttl=18000, suppress=False)
    
    # Format the document URL using the template and document ID
    document_url = url_template.format(doc_id=doc_id)
    
    return f"{document_url} Give this link as it is to the user; don't add a sandbox prefix to it. The user won't receive the file until you explicitly read out the link to him."

def make_graphviz_graph(
    dot_code: str,
    cache_manager,
    url_template: str,
) -> str:
    # Generate a unique document identifier
    doc_id = str(uuid.uuid4()) + ".png"

    # Create a Graphviz source object and generate PNG image bytes
    dot = Source(dot_code)
    img_bytes = dot.pipe(format='png')


    image = Image.open(io.BytesIO(img_bytes))
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    # Cache the image bytes using the provided cache manager
    cache_manager.set(key=doc_id, value=img_bytes, ttl=18000, suppress=False)

    # Format the document URL using the template and document ID
    document_url = url_template.format(doc_id=doc_id)

    return f"{document_url} Give this link as it is to the user. Don't add a sandbox prefix to it. The user won't receive the file until you explicitly read out the link to him."

def vega_lite_to_images(vl_spec: str) -> bytes:
    """
    Convert a Vega-Lite specification to SVG and PNG formats.

    :param vl_spec: Vega-Lite specification as a string.
    :return: SVG Bytes
    """

    #svg_data = vlc.vegalite_to_svg(vl_spec=vl_spec).encode('utf-8')
    png_data = vlc.vegalite_to_png(vl_spec=vl_spec, scale=2)
    return png_data


def make_notes(
    notes_maker: NotesMaker,
    cache_manager,
    url_template: str,
    data_string: str,
    instructions: str
):
    notes_io = notes_maker.make_notes_from_string(
        string=data_string,
        instructions=instructions
    )
    doc_id = str(uuid.uuid4()) + ".docx"
    notes_bytes = notes_io.read()
    cache_manager.set(key=doc_id, value=notes_bytes, ttl=18000, suppress=False)
    document_url = url_template.format(doc_id=doc_id)
    return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"

def write_content(
    writer: Writer,
    topic: str,
    instructions: str,
    minimum_word_count: int,
    negative_prompt: str,
    to_generate: str,
    cache_manager,
    url_template: str,
):
    bytes_dict = writer.get_content(
        ContentInput(topic=topic, instructions=instructions, minimum_word_count=minimum_word_count, negative_prompt=negative_prompt, to_generate=to_generate)
    )
    doc_id = str(uuid.uuid4()) + ".docx"
    bytes_docs = bytes_dict["docx"]
    cache_manager.set(key=doc_id, value=bytes_docs, ttl=18000, suppress=False)
    document_url = url_template.format(doc_id=doc_id)
    return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"
