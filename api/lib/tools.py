import os
import uuid
from typing import List, Dict, Union, Optional
import pypandoc
from scholarly import scholarly
from langchain.tools.base import BaseTool, StructuredTool
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)
from typing import IO
from api.lib.presentation_maker.presentation_maker import PresentationMaker, PresentationInput

class MakePresentationInput(PresentationInput):
    template_name: Optional[str] = ""


class MarkdownToPDFConverter(BaseTool):
    """Tool that converts Markdown text to a PDF file in memory."""
    
    name: str = "make_pdf"
    description: str = (
        "A tool to give the user a pdf with the content of your choice"
        "Input should be the content of the pdf in Markdown formatted string."
    )
    cache_manager: object
    url_template: str

    def _run(self, markdown_text: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> Union[IO[bytes], str]:
        """Convert Markdown text to a PDF file."""
        try:
            # Generate a unique ID for the document
            doc_id = str(uuid.uuid4())
            pdf_filename = f"/tmp/{doc_id}.pdf"

            pypandoc.convert_text(markdown_text, 'pdf', format='md', outputfile=pdf_filename, extra_args=['--pdf-engine=xelatex'])

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

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> List[Dict[str, Union[str, Optional[str]]]]:
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