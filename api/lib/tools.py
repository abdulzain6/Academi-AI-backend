import os
import random
import tempfile
import uuid
import pypandoc, pdfkit
import json
from typing import List, Dict, Union, Optional, IO
from scholarly import scholarly
from langchain.tools.base import BaseTool, Tool
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)
from api.lib.presentation_maker.presentation_maker import (
    PresentationMaker,
    PresentationInput,
)
from api.lib.uml_diagram_maker import AIPlantUMLGenerator
from langchain.pydantic_v1 import BaseModel
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)

from langchain.utilities.requests import TextRequestsWrapper
from bs4 import BeautifulSoup
from langchain.utilities.searx_search import SearxSearchWrapper

from api.routers.utils import image_to_pdf_in_memory
from ..lib.cv_maker.cv_maker import CVMaker



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


class MarkdownToPDFConverter(BaseTool):
    """Tool that converts Markdown text to a PDF file in memory."""

    name: str = "make_pdf_or_make_table"
    description: str = (
        "A tool to give the user a pdf with the content of your choice"
        "Also Can be used to gice the user a timetable a routine or any other similar doc"
        "Input should be the content of the pdf in Markdown formatted string."
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
            doc_id = f"{str(uuid.uuid4())}.pdf"
            html_filename = f"/tmp/{doc_id}.html"
            pdf_filename = f"/tmp/{doc_id}.pdf"

            # Convert Markdown to HTML
            pypandoc.convert_text(
                content,
                "html5",
                format="md",
                outputfile=html_filename,
                extra_args=["-s", "--webtex"],
            )

            # Convert HTML to PDF using wkhtmltopdf
            options = {
                "encoding": "UTF-8",
                "custom-header": [("Accept-Encoding", "gzip")],
                "no-outline": None,
            }
            pdfkit.from_file(html_filename, pdf_filename, options=options)

            with open(pdf_filename, "rb") as file:
                pdf_bytes = file.read()

            # Store the PDF in Redis
            self.cache_manager.set(
                key=doc_id, value=pdf_bytes, ttl=18000, suppress=False
            )

            # Remove the temporary HTML and PDF files
            os.remove(html_filename)
            os.remove(pdf_filename)

            # Format and return the URL with the document ID
            document_url = self.url_template.format(doc_id=doc_id)
            return document_url

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
            return f"{missing_str}. Give the following link to the user {document_url}. "
        except Exception as e:
            return f"There was an error : {e}"


def make_ppt(
    ppt_maker: PresentationMaker,
    ppt_input: MakePresentationInput,
    cache_manager,
    url_template: str,
):
    ppt_path = ppt_maker.make_presentation(
        template_name=ppt_input.template_name,
        presentation_input=PresentationInput(**ppt_input.model_dump()),
    )
    doc_id = str(uuid.uuid4()) + ".pptx"

    with open(ppt_path, "rb") as file:
        pdf_bytes = file.read()

    cache_manager.set(key=doc_id, value=pdf_bytes, ttl=18000, suppress=False)

    os.remove(ppt_path)
    document_url = url_template.format(doc_id=doc_id)
    return document_url


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
    return document_url
