from langchain.utilities.searx_search import SearxSearchWrapper
from langchain.tools.youtube.search import YouTubeSearchTool
from api.config import REDIS_URL, CACHE_DOCUMENT_URL_TEMPLATE, SEARCHX_HOST
from api.lib.database.cache_manager import RedisCacheManager
from api.lib.tools import ScholarlySearchRun, MarkdownToPDFConverter, RequestsGetTool, SearchTool
from langchain.utilities.requests import TextRequestsWrapper
import redis

CHAT_TOOLS = [
    SearchTool(
        seachx_wrapper=SearxSearchWrapper(searx_host=SEARCHX_HOST, unsecure=True, k=3)
    ),
    MarkdownToPDFConverter(
        cache_manager=RedisCacheManager(redis.from_url(REDIS_URL)),
        url_template=CACHE_DOCUMENT_URL_TEMPLATE,
    ),
    RequestsGetTool(requests_wrapper=TextRequestsWrapper()),
    YouTubeSearchTool(),
    ScholarlySearchRun(),
]
