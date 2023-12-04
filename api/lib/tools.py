import os
import uuid
import pypandoc
from typing import List, Dict, Union, Optional, IO
from scholarly import scholarly
from langchain.tools.base import BaseTool
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)
from api.lib.presentation_maker.presentation_maker import PresentationMaker, PresentationInput
from langchain.pydantic_v1 import BaseModel
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)

from langchain.utilities.requests import TextRequestsWrapper
from langchain.tools.base import BaseTool
from bs4 import BeautifulSoup


def _clean_url(url: str) -> str:
    """Strips quotes from the url."""
    return url.strip("\"'")

def strip_html(html_content: str, max_length: int = 1000) -> str:
    """Strip HTML tags and limit response length."""
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    return text[:max_length]

class BaseRequestsTool(BaseModel):
    """Base class for requests tools."""
    requests_wrapper: TextRequestsWrapper
    
class RequestsGetTool(BaseRequestsTool, BaseTool):
    """Tool for making a GET request to an API endpoint."""
    name: str = "requests_get"
    description: str = "A portal to the internet. Use this when you need to get specific content from a website. Input should be a  url (i.e. https://www.google.com). The output will be the text response of the GET request."

    def _run(self, url: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
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

    def _run(self, content: str, run_manager: Optional[CallbackManagerForToolRun] = None, *args, **kwargs) -> Union[IO[bytes], str]:
        """Convert Markdown text to a PDF file."""
        try:
            # Generate a unique ID for the document
            doc_id = str(uuid.uuid4())
            pdf_filename = f"/tmp/{doc_id}.pdf"

            pypandoc.convert_text(content, 'pdf', format='md', outputfile=pdf_filename, extra_args=['--pdf-engine=xelatex'])

            with open(pdf_filename, "rb") as file:
                pdf_bytes = file.read()
            
            # Store the PDF in Redis
            self.cache_manager.set(key=doc_id, value=pdf_bytes, ttl=18000, suppress=False)

            # Remove the temporary PDF file
            os.remove(pdf_filename)

            # Format and return the URL with the document ID
            document_url = self.url_template.format(doc_id=doc_id)
            return document_url

        except Exception as e:
            return f"An error occurred: {e}"

class ScholarlySearchRun(BaseTool):
    """Tool that queries the scholarly search API."""
    
    name: str = "scholarly_search"
    description: str = (
        "A wrapper around Scholarly Search. "
        "Useful for finding scholarly articles. "
        "Input should be a search query."
    )

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None, *args, **kwargs) -> List[Dict[str, Union[str, Optional[str]]]]:
        """Use the tool."""
        search_query = scholarly.search_pubs(query)
        results: List[Dict[str, Union[str, Optional[str]]]] = []
        count = 0
        while count < 6:
            try:
                paper = next(search_query)
                title = paper['bib'].get('title', 'N/A')
                authors = paper['bib'].get('author', 'N/A')
                year = paper['bib'].get('pub_year', 'N/A')
                pdf_url = paper.get('eprint_url', 'N/A')
                
                results.append({
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "url": pdf_url  # Prioritize eprint_url for PDF
                })

                count += 1
            except StopIteration:
                # No more papers to process
                break
            except Exception as e:
                return f"An error occurred: {e}"

        return results

def make_ppt(ppt_maker: PresentationMaker, ppt_input: MakePresentationInput, cache_manager, url_template: str):
    ppt_path = ppt_maker.make_presentation(template_name=ppt_input.template_name, presentation_input=PresentationInput(**ppt_input.model_dump()))
    doc_id = str(uuid.uuid4()) + ".pptx"

    with open(ppt_path, "rb") as file:
        pdf_bytes = file.read()
    
    cache_manager.set(key=doc_id, value=pdf_bytes, ttl=18000, suppress=False)
    
    os.remove(ppt_path)
    document_url = url_template.format(doc_id=doc_id)
    return document_url