from langchain.tools.ddg_search.tool import DuckDuckGoSearchRun
from langchain.tools.youtube.search import YouTubeSearchTool
import redis
from api.config import REDIS_URL, CACHE_DOCUMENT_URL_TEMPLATE
from api.lib.database.cache_manager import RedisCacheManager
from api.lib.tools import ScholarlySearchRun, MarkdownToPDFConverter, RequestsGetTool
from langchain.utilities.requests import TextRequestsWrapper

CHAT_TOOLS = [
    #DuckDuckGoSearchRun(),
    MarkdownToPDFConverter(
        cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
        url_template=CACHE_DOCUMENT_URL_TEMPLATE,
    ),
    RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
    YouTubeSearchTool(),
    ScholarlySearchRun(),
]
