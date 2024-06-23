from abc import abstractmethod
import os
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta
from cycletls_client import CycleTlsServerClient
from bs4 import BeautifulSoup
from lxml import html
from urllib.parse import urlparse, urlunparse
from database import CourseRepository, Course
import re
import requests

    
        
class CourseScraper:
    def __init__(self, cycle_tls_client: CycleTlsServerClient, base_url: str, max_limit: int = 200, max_loops: int = 5) -> None:
        self.base_url = base_url
        self.max_limit = max_limit
        self.cycle_tls_client = cycle_tls_client
        self.max_loops = max_loops
    
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
    
    def extract_image_url(self, html_content: str) -> str | None:
        """
        Extracts the image URL from the HTML meta tags.

        Args:
            html_content (str): The HTML content as a string.

        Returns:
            str | None: The URL of the image if found, otherwise None.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the meta tag with property 'og:image'
        og_image = soup.find('meta', property='og:image')
        if og_image and 'content' in og_image.attrs:
            return og_image['content']
        
        # If the 'og:image' tag is not found, return None
        return None

    def validate_link_and_get_price(self, url: str) -> tuple[bool, float, float, str]:
        try:
            html_content = self.cycle_tls_client.get(url, use_proxy=True).json()
            html_body = html_content["body"]
            html_request_status = html_content["status"]            
            if html_request_status in (301, 302) or "is no longer available" in html_body or "no longer" in html_body:
                print("No longer available in body")
                return False, 0.0, 0.0, datetime.now() + timedelta(days=5), None
        
            soup = BeautifulSoup(html_body, "html.parser")
            course_id = soup.find("body").get("data-clp-course-id")
            image = self.extract_image_url(html_body)
            if not course_id:
                raise ValueError("Course ID not found.")
            
            
            api_url = self.make_api_url(url, course_id)          
            response = self.cycle_tls_client.get(api_url, use_proxy=True).json()
            
            if response["status"] != 200:
                print("Status not 200", response["status"])
                return False, 0.0, 0.0, datetime.now() + timedelta(days=5), None
            
            data = response["body"]
            price_data = data["price_text"]["data"]["pricing_result"]
            sale_price = price_data["price"]["amount"]
            actual_price = price_data["list_price"]["amount"]
            end_date = price_data["campaign"]["end_time"]
            
            return True, sale_price, actual_price, end_date, image

        except Exception as e:
            print(e)
            return False, 0.0, 0.0, datetime.now() + timedelta(days=5), None
    
    @staticmethod
    def is_udemy_domain(input_url):
        parsed_url = urlparse(input_url)
        return parsed_url.hostname == 'www.udemy.com'

    @staticmethod
    def get_final_url(input_url):
        try:
            response = requests.get(input_url, allow_redirects=True, timeout=30)
            print(response.status_code)
            return response.url
        except requests.RequestException as e:
            print(f"Error fetching URL: {e}")
            return input_url
        
class RealDiscount(CourseScraper):
    def scrape(self) -> list[Course]:
        courses = []
        page = 1

        while len(courses) < self.max_limit:
            if page > self.max_loops:
                break
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
                        valid, _, _, end_date, image = self.validate_link_and_get_price(url)
                        if not valid:
                            raise ValueError("Invalid Result")

                        courses.append(
                            Course(
                                name=result.get('name'),
                                category=result.get('category'),
                                image=image if image else result.get('image'),
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

        return courses
            
class OnlineCourses(CourseScraper):
    def get_link_tags_and_description(self, url: str) -> tuple[str, list[str], str]:
        response = self.cycle_tls_client.get(url).json()
        if not str(response["status"]).startswith("20"):
            raise ValueError("Cannot enter page to get link")
        
        html_body = response["body"]
        tree = html.fromstring(html_body)
        
        # Extract the link
        link_element = tree.xpath('//a[@class="btn_offer_block re_track_btn"]/@href')
        if not link_element:
            raise ValueError("Coupon link not found")
        
        link = link_element[0]

        try:
            tags_elements = tree.xpath('//div[@class="tags mb25"]//a[@rel="tag"]/text()')
            tags = [tag.strip() for tag in tags_elements]
        except Exception:
            tags = ["Unknown"]
        
        try:
            description_element = tree.xpath('//div[@data-purpose="safely-set-inner-html:description:description"]')[0]
            for script in description_element.xpath('.//script | .//style'):
                script.getparent().remove(script)
            description = ' '.join(description_element.xpath('.//text()[normalize-space()]')).strip()
        except Exception:
            description = "No description available"

        return link, tags, description
        
    def extract_courses_from_html(self, html_content: str) -> list[Course]:
        tree = html.fromstring(html_content)
        articles = tree.xpath('//article[contains(@class, "offer_grid")]')

        courses = []
        for article in articles:
            try:
                name = article.xpath('.//h3/a/text()')[0].strip()
                url = article.xpath('.//h3/a/@href')[0].strip()
                url, tags, description = self.get_link_tags_and_description(url)
                
                image_element = article.xpath('.//figure/a/img/@data-src')
                if not image_element:
                    image_element = article.xpath('.//figure/a/img/@src')
                image = image_element[0].strip() if image_element else "No image available"

                current_price_text = article.xpath('.//span[@class="rh_regular_price"]/text()')[0].strip()
                current_price = 0.0 if current_price_text.lower() == "free" else float(re.sub(r'[^\d.]', '', current_price_text))
                try:
                    actual_price_text = article.xpath('.//del/text()')[0].strip()
                    actual_price = float(re.sub(r'[^\d.]', '', actual_price_text))
                except Exception:
                    actual_price = 0
                
                valid, _, _, end_date, image_link = self.validate_link_and_get_price(url)
                if not valid and actual_price != 0:
                    raise ValueError("Invalid Result")   
            
                     
                courses.append(
                    Course(
                        name=name,
                        image=image_link if image_link else image,
                        category=tags[0],
                        actual_price_usd=actual_price,
                        sale_price_usd=current_price,
                        description=description,
                        url=url,
                        sale_end=end_date
                    )
                )
            except Exception as e:
                import traceback
                print(f"Error extracting course information: {traceback.format_exception(e)} { name}")
        
        return courses

    def scrape(self, *args, **kwargs) -> list[Course]:
        courses = []
        page_number = 1

        while len(courses) < self.max_limit:
            full_url = f"{self.base_url}page/{page_number}/"
            if page_number > self.max_loops:
                break
            
            try:
                response = self.cycle_tls_client.get(full_url).json()
                if not str(response["status"]).startswith("20"):
                    raise ValueError("Cannot enter page")
                
                html_body = response["body"]
                new_courses = self.extract_courses_from_html(html_content=html_body)
                courses.extend(new_courses)

                if not new_courses:  # If no more courses are found, break the loop
                    break

            except Exception as e:
                import traceback
                print(f"Error on page {page_number}: {traceback.format_exc()}")

            page_number += 1

            # Stop if we reach max_limit
            if len(courses) >= self.max_limit:
                break

        # Trim the list to max_limit if it exceeds
        return courses[:self.max_limit]
        
class CouponEagle(CourseScraper):
    def extract_course_link_and_tags(self, html_content: str) -> tuple[str, list[str]]:
        tree = html.fromstring(html_content)
        link = tree.xpath('//a[@class="btn_offer_block re_track_btn"]/@href')[0].strip()        
        try:
            tags_element = tree.xpath('//div[@class="tags mb25"]')[0]
            tags = tags_element.xpath('.//a[@rel="tag"]/text()')
            tags = [tag.strip() for tag in tags]
        except IndexError:
            tags = ["General"]
        
        return link, tags

    def extract_courses_from_html(self, html_content: str) -> list[Course]:
        tree = html.fromstring(html_content)
        course_elements = tree.xpath('//div[contains(@class, "news-community clearfix")]')
        
        courses = []
        for element in course_elements:
            try:
                name = element.xpath('.//h2[@class="font130 mt0 mb10 mobfont120 lineheight25"]/a/text()')[0].strip()
                link = element.xpath('.//h2[@class="font130 mt0 mb10 mobfont120 lineheight25"]/a/@href')[0].strip()
                description = element.xpath('.//div[contains(@class, "rh_gr_right_desc")]/p/text()')[0].strip()
                image = element.xpath('.//figure/a/img/@data-src | .//figure/a/img/@src')[0].strip()

                response = self.cycle_tls_client.get(link).json()
                if not str(response["status"]).startswith("20"):
                    raise ValueError("Cannot enter page")
                
                link, tags = self.extract_course_link_and_tags(response["body"])
                valid, sale_price, actual_price, end_date, image_link = self.validate_link_and_get_price(link)
                if not valid and actual_price != 0:
                    raise ValueError("Invalid Result") 
                        
                courses.append(
                    Course(
                        name=name,
                        category=tags[0],
                        image=image_link if image_link else image,
                        actual_price_usd=actual_price,
                        sale_price_usd=sale_price,
                        sale_end=end_date,
                        description=description,
                        url=link
                    )
                )
            except Exception as e:
                print(f"Error extracting information for one of the courses: {e}")
        
        return courses
    
    def scrape(self) -> list[Course]:
        courses = []
        page_number = 1

        while len(courses) < self.max_limit:
            full_url = f"{self.base_url}page/{page_number}/"
            if page_number > self.max_loops:
                break
            
            try:
                response = self.cycle_tls_client.get(full_url).json()
                if not str(response["status"]).startswith("20"):
                    raise ValueError("Cannot enter page")
                
                new_courses = self.extract_courses_from_html(response["body"])
                courses.extend(new_courses)

                if not new_courses:  # If no more courses are found, break the loop
                    break

            except Exception as e:
                import traceback
                print(f"Error on page {page_number}: {traceback.format_exc()}")

            page_number += 1

        return courses

class CouponScorpion(CourseScraper):
    def extract_course_details(self, content: str) -> tuple[str, str]:
        tree = html.fromstring(content)
        
        description = tree.xpath('//div[@class="rh-flex-grow1 single_top_main mr20"]/div/p/text()')
        description = description[0].strip() if description else "No description available"
        
        course_link = f"https://couponscorpion.com/scripts/udemy/out.php?go={self.extract_js_variable(content, 'sf_offer_url')}"
        
        if not course_link:
            raise ValueError("No course link found")

        return description, course_link
    
    def get_udemy_link(self, link: str) -> str:
        response = self.cycle_tls_client.get(link,
            headers = {
                'authority': 'couponscorpion.com',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'accept-language': 'en-US,en;q=0.9',
                'dnt': '1',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Linux"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        )
        return response.json()['finalUrl']

    def extract_js_variable(self, html_content: str, variable_name: str) -> str:
        # Create a regex pattern to match the variable assignment
        pattern = rf"var {re.escape(variable_name)}\s*=\s*'([^']+)';"
        
        # Search for the pattern in the HTML content
        match = re.search(pattern, html_content)
        
        # Return the matched string or None if not found
        return match.group(1) if match else None

    def extract_courses_from_html(self, html_content: str) -> list[Course]:
        tree = html.fromstring(html_content)
        course_elements = tree.xpath('//article[contains(@class, "col_item offer_grid")]')
        
        courses = []
        for element in course_elements:
            try:
                name = element.xpath('.//h3/a/text()')[0].strip()
                link = element.xpath('.//h3/a/@href')[0].strip()
                image = element.xpath('.//figure/a/img/@src')[0].strip()
                tag = element.xpath('.//div[@class="cat_for_grid lineheight15"]/span/a/text()')[0].strip()
                
                response = self.cycle_tls_client.get(link).json()
                if not str(response["status"]).startswith("20"):
                    raise ValueError("Cannot enter page")
                
                description, course_link = self.extract_course_details(response["body"])
                print(course_link)
                course_link = self.get_udemy_link(course_link)
                valid, sale_price, actual_price, end_date, image_link = self.validate_link_and_get_price(course_link)
                if not valid and actual_price != 0:
                    raise ValueError("Invalid Result") 
                
                courses.append(
                    Course(
                        name=name,
                        category=tag,
                        image=image_link if image_link else image,
                        actual_price_usd=actual_price,
                        sale_price_usd=sale_price,
                        sale_end=end_date,
                        description=description,
                        url=course_link
                    )
                )
            except Exception as e:
                print(f"Error extracting information for one of the courses: {e}")
        
        return courses
    
    def scrape(self) -> list[Course]:
        courses = []
        page_number = 1

        while len(courses) < self.max_limit:
            full_url = f"{self.base_url}page/{page_number}/"
            if page_number > self.max_loops:
                break
            try:
                response = self.cycle_tls_client.get(full_url).json()
                if not str(response["status"]).startswith("20"):
                    print(response["body"])
                    raise ValueError("Cannot enter page")
                
                new_courses = self.extract_courses_from_html(response["body"])
                courses.extend(new_courses)

                if not new_courses:  # If no more courses are found, break the loop
                    break

            except Exception as e:
                import traceback
                print(f"Error on page {page_number}: {traceback.format_exc()}")

            page_number += 1

        return courses[:self.max_limit]


def remove_url_parameters(url: str) -> str:
    parsed_url = urlparse(url)
    clean_url = urlunparse(parsed_url._replace(query=""))
    return clean_url

def remove_duplicates(courses: list[Course]) -> list[Course]:
    unique_courses = {}
    for course in courses:
        clean_url = remove_url_parameters(course.url)
        if clean_url not in unique_courses:
            unique_courses[clean_url] = course
    return list(unique_courses.values())



if __name__ == "__main__":
    database = CourseRepository(
        os.getenv("MONGODB_URL"),
        os.getenv("DATABASE_NAME", "study-app"),
        os.getenv("COLLECTION_NAME", "courses")
    )
    max_limit = int(os.getenv("MAX_LIMIT", 30))
    cycle_tls_url = os.getenv("CYCLETLS_URL", "http://localhost:3000/")
    max_pages = int(os.getenv("MAX_PAGES", 3))
    proxy = os.getenv("PROXY_URL", "http://dprulefr-rotate:7obapq1qv8fl@p.webshare.io:80")
    
    scrapers: list[CourseScraper] = [
        CouponScorpion(
            cycle_tls_client=CycleTlsServerClient(f"{cycle_tls_url}fetch", proxy=proxy),
            base_url="https://couponscorpion.com/",
            max_limit=max_limit,
            max_loops=max_pages
        ),
        CouponEagle(
            cycle_tls_client=CycleTlsServerClient(f"{cycle_tls_url}fetch", proxy=proxy),
            base_url="https://www.couponseagle.com/",
            max_limit=max_limit,
            max_loops=max_pages
        ),
        RealDiscount(
            cycle_tls_client=CycleTlsServerClient(f"{cycle_tls_url}fetch", proxy=proxy),
            base_url="https://www.real.discount/",
            max_limit=max_limit,
            max_loops=max_pages
        ),
        OnlineCourses(
            cycle_tls_client=CycleTlsServerClient(f"{cycle_tls_url}fetch", proxy=proxy),
            base_url="https://www.onlinecourses.ooo/",
            max_limit=max_limit,
            max_loops=max_pages
        ),
    ]
    courses = []
    for scraper in scrapers:
        try:
            courses.extend(scraper.scrape())
            print(f"Total courses : {len(courses)}")
        except Exception as e:
            print(e)
    
    courses = remove_duplicates(courses)
    database.save_courses(courses)
    

    
