from fastapi import APIRouter, Depends, HTTPException
from .auth import verify_token
from pydantic import BaseModel, Field
from api.gpts_lib.amazon_search import AmazonScraper, CycleTlsServerClient, SortOptions, DetailedProduct, transform_to_affiliate_link
from api.globals import CYCLE_TLS_SERVER_URL, AFFILIATE_TAG, HTTP_PROXY_URL


router = APIRouter()

class SearchAmazonRequest(BaseModel):
    base_amazon_url: str = Field("https://www.amazon.com", json_schema_extra={"description" : "The base amazon url to use this will depend ont he country of the user."})
    sort_by: SortOptions = Field(SortOptions.FEATURED, json_schema_extra={"description" : "Criteria to sort results by"})
    query: str = Field(json_schema_extra={"description" : "The search query"})
    num_results: int = Field(json_schema_extra={"description" : "The number of results to return"})
    find_deals: bool = Field(False, json_schema_extra={"description" : "Whether to look for offers and deals"})

class GetProductsRequest(BaseModel):
    product_link: str = Field(..., description="The direct link to the Amazon product")
    base_amazon_url: str = Field("https://www.amazon.com", json_schema_extra={"description" : "The base amazon url to use this will depend ont he country of the user."})

class BrowseAmazonRequest(BaseModel):
    link: str = Field(..., description="The URL of the Amazon page to convert to markdown")
    base_amazon_url: str = Field("https://www.amazon.com", json_schema_extra={"description" : "The base amazon url to use this will depend ont he country of the user."})

def add_tag(link: str) -> str:
    return transform_to_affiliate_link(link, AFFILIATE_TAG)

@router.post("/search-amazon",
    description="Searches for products on Amazon based on user-provided criteria. This endpoint allows users to specify a base Amazon URL (which can vary by country), a search query, sorting criteria, the number of results to return, and an option to focus on finding deals. This endpoint is ideal for users who want to customize their Amazon product search experience according to their specific needs, such as finding deals or searching in a specific Amazon regional website.",
    openapi_extra={"x-openai-isConsequential": False}
)
def search_amazon(
    search_request: SearchAmazonRequest,
    _=Depends(verify_token),
):     
    try:
        scraper = AmazonScraper(search_request.base_amazon_url, CycleTlsServerClient(server_url=CYCLE_TLS_SERVER_URL, proxy=HTTP_PROXY_URL), link_convertor=add_tag)
        return scraper.search(
            keyword=search_request.query,
            num_results=min(10, search_request.num_results),
            sort_by=search_request.sort_by,
            find_deals=search_request.find_deals
        )
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    
    
@router.post("/get-product-details",
    description="Retrieves detailed information about a specific product from Amazon. This endpoint requires a direct link to the Amazon product. It returns various details about the product such as title, rating, description, number of reviews, product image, additional product information, product features, seller name and link, and any available video URLs. This endpoint is suitable for users who require comprehensive details about a specific product, enhancing their understanding of the product's features and seller information.",
    openapi_extra={"x-openai-isConsequential": False}
)
def get_product_details(
    request: GetProductsRequest,
    _=Depends(verify_token),
):
    try:
        scraper = AmazonScraper(request.base_amazon_url, CycleTlsServerClient(server_url=CYCLE_TLS_SERVER_URL, proxy=HTTP_PROXY_URL))
        return scraper.get_product_details(request.product_link)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post("/browse-amazon",
    description="Converts the content of an Amazon page into clean markdown format. This endpoint takes a URL to any Amazon page and returns the page's content in markdown. It's useful for extracting readable and formatted text from Amazon pages, which can be beneficial for various applications such as content aggregation, research, or data analysis. The markdown content includes text and structure but does not include images or complex styling from the original webpage.",
    response_model=str,
    openapi_extra={"x-openai-isConsequential": False}
)
def browse_amazon(
    browse_request: BrowseAmazonRequest,
    _=Depends(verify_token),
) -> str:
    try:
        scraper = AmazonScraper(browse_request.base_amazon_url, CycleTlsServerClient(server_url=CYCLE_TLS_SERVER_URL, proxy=HTTP_PROXY_URL))
        return scraper.browse_amazon(browse_request.link)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
