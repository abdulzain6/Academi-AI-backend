from abc import ABC, abstractmethod
import re
from pydantic import BaseModel
from datetime import datetime
import requests

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
    def __init__(self, *args, **kwargs) -> None:
        pass
    
    @abstractmethod
    def scrape(self, *args, **kwargs) -> list[Course]:
        pass
    
    @abstractmethod
    def validate_courses(self, courses: list[Course]) -> list[Course]:
        pass
    
    @abstractmethod
    def run(self, *args, **kwargs) -> list[Course]:
        pass
    

class RealDiscounr(CourseScraper):
    def __init__(self, base_url: str = "https://www.real.discount/", max_limit: int = 200) -> None:
        self.base_url = base_url
        self.max_limit = max_limit
        
    def scrape(self) -> list[Course]:
        courses = []
        params = {
            'store': 'Udemy',
            'page': '2',
            'per_page': '10',
            'orderby': 'date',
            'free': '1',
            'search': '',
            'language': '',
            'cat': 'all',
        }
        response = requests.get(f'{self.base_url}api-web/all-courses/', params=params)
        response.raise_for_status()
        results = response.json()["results"]
        for result in results:
            courses.append(
                Course(
                    name=result.get('name'),
                    category=result.get('category'),
                    image=result.get('image'),
                    actual_price_usd=float(re.sub(r'[^\d.]', '', result.get('price'))),
                    sale_price_usd= float(re.sub(r'[^\d.]', '', result.get('sale_price'))),
                    description=result.get('shoer_description'),
                    url=result.get('url'),
                    
                )
            )
            
        
        