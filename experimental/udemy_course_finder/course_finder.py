from abc import abstractmethod
from pydantic import BaseModel
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
from cycletls_client import CycleTlsServerClient
from bs4 import BeautifulSoup

import re
import requests
import json

class Course(BaseModel):
    name: str
    category: str
    image: str | None = None
    actual_price_usd: float
    sale_price_usd: float
    sale_end: datetime
    description: str | None = None
    url: str
    
        
class CourseScraper:
    def __init__(self, cycle_tls_client: CycleTlsServerClient, *args, **kwargs) -> None:
        self.cycle_tls_client = cycle_tls_client
    
    @abstractmethod
    def scrape(self, *args, **kwargs) -> list[Course]:
        pass
    
    @abstractmethod
    def validate_courses(self, courses: list[Course]) -> list[Course]:
        pass
    
    @abstractmethod
    def run(self, *args, **kwargs) -> list[Course]:
        pass

    def make_api_url(self, url: str, course_id: int) -> str:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        coupon_code = query_params.get("couponCode", ["FREE"])[0]
        api_url = (f"https://www.udemy.com/api-2.0/course-landing-components/{course_id}/me/"
                f"?couponCode={coupon_code}&utm_source=aff-campaign&utm_medium=udemyads&components=redeem_coupon,price_text")
        return unquote(api_url)

    def validate_link_and_get_price(self, url: str) -> tuple[bool, float, float, str]:
        try:
            html_content = self.cycle_tls_client.get(url).json()
            html_body = html_content["body"]
            html_request_status = html_content["status"]            
            if html_request_status in (301, 302) or "is no longer available" in html_body or "no longer" in html_body:
                print("No longer available in body")
                return False, 0.0, 0.0, ""
        
            soup = BeautifulSoup(html_body, "html.parser")
            course_id = soup.find("body").get("data-clp-course-id")
            
            if not course_id:
                raise ValueError("Course ID not found.")
            
            
            api_url = self.make_api_url(url, course_id)          
            response = self.cycle_tls_client.get(api_url).json()
            
            if response["status"] != 200:
                return False, 0.0, 0.0, ""
            
            data = response["body"]
            price_data = data["price_text"]["data"]["pricing_result"]
            sale_price = price_data["price"]["amount"]
            actual_price = price_data["list_price"]["amount"]
            end_date = price_data["campaign"]["end_time"]

            return True, sale_price, actual_price, end_date

        except Exception as e:
            print(e)
            return False, 0.0, 0.0, ""
    
    @staticmethod
    def is_udemy_domain(input_url):
        parsed_url = urlparse(input_url)
        return parsed_url.hostname == 'www.udemy.com'

    @staticmethod
    def get_final_url(input_url):
        try:
            response = requests.get(input_url, allow_redirects=True, timeout=30)
            return response.url
        except requests.RequestException as e:
            print(f"Error fetching URL: {e}")
            return input_url
        
        
        
class RealDiscount(CourseScraper):
    def __init__(self, cycle_tls_client: CycleTlsServerClient, base_url: str = "https://www.real.discount/", max_limit: int = 200) -> None:
        self.base_url = base_url
        self.max_limit = max_limit
        self.cycle_tls_client = cycle_tls_client
        
    def scrape(self) -> list[Course]:
        courses = []
        page = 1

        while len(courses) < self.max_limit:
            try:
                params = {
                    'store': 'Udemy',
                    'page': str(page),
                    'per_page': '10',
                    'orderby': 'undefined',
                    'free': '1',
                    'search': '',
                    'language': '',
                    'cat': '',
                }
                response = requests.get(f'{self.base_url}api-web/all-courses/', params=params)
                response.raise_for_status()
                results = response.json()["results"]

                if not results:
                    break  # Exit if no more results are returned

                for result in results:
                    try:
                        if not result.get('url') or not result.get('image'):
                            raise ValueError("Result has no url or no image")

                        if self.is_udemy_domain(result.get('url')):
                            url = result.get('url')
                        else:
                            url = self.get_final_url(result.get('url'))

                        print(f"Url in {url}")
                        valid, _, _, end_date = self.validate_link_and_get_price(url)
                        if not valid:
                            raise ValueError("Invalid Result")

                        courses.append(
                            Course(
                                name=result.get('name'),
                                category=result.get('category'),
                                image=result.get('image'),
                                actual_price_usd=float(re.sub(r'[^\d.]', '', str(result.get('price')))),
                                sale_price_usd=float(re.sub(r'[^\d.]', '', str(result.get('sale_price')))),
                                description=result.get('shoer_description'),
                                url=result.get('url'),
                                sale_end=end_date
                            )
                        )

                        if len(courses) >= self.max_limit:
                            break  # Exit if max limit is reached

                    except Exception as e:
                        import traceback
                        print(f"Error: {traceback.format_exc()}, {result}")

                page += 1  # Move to the next page

            except Exception as e:
                import traceback
                print(f"Error: {traceback.format_exc()} during pagination or fetching results")
                break  # Exit loop if fetching or parsing results fails

        return courses
            
        
if __name__ == "__main__":
    rd = RealDiscount(cycle_tls_client=CycleTlsServerClient("http://localhost:3000/fetch"))
    print(rd.scrape())