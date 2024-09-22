from datetime import datetime
import os
from cycletls_client import CycleTlsServerClient
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, unquote
from pymongo import MongoClient, ASCENDING, DeleteOne
from pymongo.errors import BulkWriteError
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from urllib.parse import urlparse, urlunparse

def remove_url_parameters(url: str) -> str:
    parsed_url = urlparse(url)
    clean_url = urlunparse(parsed_url._replace(query=""))
    return clean_url

class Course(BaseModel):
    name: str
    category: str
    image: Optional[str] = None
    actual_price_usd: float
    sale_price_usd: float
    sale_end: datetime
    description: Optional[str] = None
    url: str
    clean_url: str = Field(default="")

    def __init__(self, **data):
        super().__init__(**data)
        self.clean_url = remove_url_parameters(self.url)



class CourseValidator:
    def __init__(self, cycle_tls_client: CycleTlsServerClient) -> None:
        self.cycle_tls_client = cycle_tls_client
        
    def make_api_url(self, url: str, course_id: int) -> str:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        coupon_code = query_params.get("couponCode", ["FREE"])[0]
        api_url = (f"https://www.udemy.com/api-2.0/course-landing-components/{course_id}/me/"
                f"?couponCode={coupon_code}&utm_source=aff-campaign&utm_medium=udemyads&components=redeem_coupon,price_text")
        return unquote(api_url)
    
    def validate_link_and_get_price(self, url: str):
        try:
            html_content = self.cycle_tls_client.get(url, use_proxy=True).json()
            html_body = html_content["body"]
            html_request_status = html_content["status"]            
            if html_request_status in (301, 302) or "is no longer available" in html_body or "no longer" in html_body:
                print("No longer available in body")
                return False
        
            soup = BeautifulSoup(html_body, "html.parser")
            course_id = soup.find("body").get("data-clp-course-id")
            if not course_id:
                raise ValueError("Course ID not found.")
            
            
            api_url = self.make_api_url(url, course_id)          
            response = self.cycle_tls_client.get(api_url, use_proxy=True).json()
            
            if response["status"] != 200:
                print("Status not 200", response["status"])
                return False
            
            data = response["body"]
            price_data = data["price_text"]["data"]["pricing_result"]
            sale_price = price_data["price"]["amount"]
            assert sale_price == 0, f"Sale price not 0, but {sale_price}"
            return True
        except (AssertionError, ValueError) as e:
            print(e)
            return False            
        except Exception as e:
            print(e)
            return True
        
    def remove_courses_based_on_filter(self, uri: str, db_name: str, collection_name: str):
        client = MongoClient(uri)
        db = client[db_name]
        collection = db[collection_name]

        # Create TTL index for sale_end
        collection.create_index([("sale_end", ASCENDING)], expireAfterSeconds=0)

        cursor = collection.find()
        delete_operations = []
        for doc in cursor:
            course = Course(**doc)
            if not self.validate_link_and_get_price(course.url):
                print(f"Deleting {course.url}")
                delete_operations.append(
                    DeleteOne({"_id": doc["_id"]})
                )
            else:
                print(f"Letting {course.url} be.")
        if delete_operations:
            try:
                collection.bulk_write(delete_operations, ordered=False)
            except BulkWriteError as e:
                print(f"Bulk write error: {e.details}")
            
if __name__ == "__main__":
    cycle_tls_url = os.getenv("CYCLETLS_URL", "http://localhost:3000/")
    proxy = os.getenv("PROXY_URL", "http://dprulefr-rotate:7obapq1qv8fl@p.webshare.io:80")
    validator = CourseValidator(CycleTlsServerClient(f"{cycle_tls_url}fetch", proxy=proxy))
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("DATABASE_NAME", "study-app")
    collection_name = os.getenv("COLLECTION_NAME", "courses")
    
    validator.remove_courses_based_on_filter(uri=mongo_url, db_name=db_name, collection_name=collection_name)