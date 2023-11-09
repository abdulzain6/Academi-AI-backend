from typing import List, Dict, Union, Optional
from scholarly import scholarly
from langchain.tools.base import BaseTool
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)

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


