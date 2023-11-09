from langchain.tools.ddg_search.tool import DuckDuckGoSearchRun
from langchain.tools.wikipedia.tool import WikipediaQueryRun
from langchain.utilities.wikipedia import WikipediaAPIWrapper
from langchain.tools.youtube.search import YouTubeSearchTool

from api.lib.tools import ScholarlySearchRun

CHAT_TOOLS = [
    DuckDuckGoSearchRun(),
    WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()),
    YouTubeSearchTool(),
    ScholarlySearchRun()
]