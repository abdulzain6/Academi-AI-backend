from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl
from typing import List
from enum import Enum
import socket
import subprocess
import re
import time
import requests
import html2text


class Product(BaseModel):
    title: str
    url: HttpUrl
    price: str
    rating: float
    number_of_ratings: str
    asin: str
    image_url: str

class DetailedProduct(BaseModel):
    title: str
    rating: float
    price: str
    description: str
    number_of_reviews: int
    product_image: str
    product_information_string: str
    product_feature_string: str
    seller_name: str
    seller_link: str
    video_urls: list[str]

class SortOptions(Enum):
    FEATURED = "FEATURED"
    PRICE_LOW_TO_HIGH = "PRICE_LOW_TO_HIGH"
    PRICE_HIGH_TO_LOW = "PRICE_HIGH_TO_LOW"
    REVIEW_RANK = "REVIEW_RANK"
    NEWEST_ARRIVALS = "NEWEST_ARRIVALS"
    BEST_SELLERS = "BEST_SELLERS"

sort_options_mapping = {
    SortOptions.FEATURED: "relevanceblender",
    SortOptions.PRICE_LOW_TO_HIGH: "price-asc-rank",
    SortOptions.PRICE_HIGH_TO_LOW: "price-desc-rank",
    SortOptions.REVIEW_RANK: "review-rank",
    SortOptions.NEWEST_ARRIVALS: "date-desc-rank",
    SortOptions.BEST_SELLERS: "exact-aware-popularity-rank",
}

def find_free_port():
    """Finds a free port on the host machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

import re

def transform_to_affiliate_link(product_url: str, affiliate_tag: str) -> str:
    """
    Transforms an Amazon product or deal link into an affiliate link.

    :param product_url: str - The original product or deal URL from Amazon.
    :param affiliate_tag: str - Your unique Amazon affiliate tag.
    :return: str - The transformed affiliate URL.
    """
    if not product_url or not affiliate_tag:
        raise ValueError("Product URL and affiliate tag are required")

    # Check if the URL contains an ASIN
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', product_url)

    if asin_match:
        # If an ASIN is found, create a short link using the ASIN
        asin = asin_match.group(1)
        new_url = f"https://www.amazon.com/dp/{asin}/?tag={affiliate_tag}"
    else:
        # If no ASIN is found, append the affiliate tag to the existing URL
        parsed_url = urlparse(product_url)
        query_params = parse_qs(parsed_url.query)

        # Add or update the affiliate tag
        query_params['tag'] = [affiliate_tag]

        # Construct the new URL with the updated affiliate tag
        new_query_string = urlencode(query_params, doseq=True)
        new_url = urlunparse(parsed_url._replace(query=new_query_string))

    return new_url

class CycleTlsServerClient:
    def __init__(self, server_url: str, default_args: dict = None, proxy: str = None):
        self.server_url = server_url
        if not default_args:
            self.default_args = {
                "body": "",
                "ja3": "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,17513-11-45-23-27-51-5-18-10-65037-13-43-35-16-65281-0,29-23-24,0",
                "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                "headers": {
                    "authority": "www.amazon.com",
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "accept-language": "en-US,en;q=0.9",
                    "cache-control": "max-age=0",
                    "device-memory": "4",
                    "dnt": "1",
                    "downlink": "3.35",
                    "dpr": "1",
                    "ect": "4g",
                    "rtt": "150",
                    "sec-ch-device-memory": "4",
                    "sec-ch-dpr": "1",
                    "sec-ch-ua": '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Linux"',
                    "sec-ch-viewport-width": "537",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                    "viewport-width": "537",
                },
                "proxy": proxy
            }
        else:
            self.default_args = default_args

    def send_request(self, get_url: str):
        response = requests.post(
            self.server_url, json={"args": self.default_args, "url": get_url}
        )
        return response.json()["body"]
    
class AmazonScraper:
    def __init__(self, base_url: str, client: CycleTlsServerClient, link_convertor: callable = None):
        base_url = base_url.rstrip("/")
        self.base_url = base_url
        self.chrome_port = find_free_port()
        self.chrome_process = None
        self.client = client
        self.link_convertor = link_convertor
        # self.start_chrome()

    def start_chrome(self):
        """Starts a headless Chrome instance with a dynamic port."""
        if self.chrome_process is None:
            self.chrome_process = subprocess.Popen(
                [
                    "google-chrome",
                    f"--remote-debugging-port={self.chrome_port}",
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-css",
                    "--disable-images",
                    "--blink-settings=imagesEnabled=false",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                ]
            )
            time.sleep(3)  # Wait for Chrome to start

    def stop_chrome(self):
        """Stops the headless Chrome instance."""
        if self.chrome_process:
            self.chrome_process.kill()
            self.chrome_process = None

    def get_page_content(
        self, keyword: str, page_number: int, sort_by: SortOptions = None, find_deals: bool = False
    ) -> str:
        """Fetches the content of a search results page using headless Chrome."""
        params = {
            'k': quote_plus(keyword),
            's': quote_plus(sort_options_mapping.get(sort_by, 'relevanceblender')),
            'page': page_number
        }

        if find_deals:
            params['i'] = 'todays-deals'

        # Add more parameters here as needed

        search_url = f"{self.base_url}/s?{urlencode(params)}"
        return self.client.send_request(search_url)

        # browser = pychrome.Browser(url=f"http://127.0.0.1:{self.chrome_port}")
        # tab = browser.new_tab()

        # try:
        #   tab.start()
        #  tab.Network.enable()
        # tab.Page.navigate(url=search_url, _timeout=10)
        # tab.wait(5)  # wait for the page to load
        # html_content = tab.Runtime.evaluate(expression="document.documentElement.outerHTML")['result']['value']
        # finally:
        #   browser.close_tab(tab)

        return html_content

    def extract_single_page_products(self, html_content: str) -> List[Product]:
        soup = BeautifulSoup(html_content, "html.parser")
        products_list = []
        product_divs = soup.find_all("div", {"data-component-type": "s-search-result"})
            
        for div in product_divs:
            # Title extraction
            title = (
                div.find("h2").get_text().strip()
                if div.find("h2")
                else "Title not available"
            )

            # URL extraction
            relative_url = (
                div.find("a", class_="a-link-normal")["href"]
                if div.find("a", class_="a-link-normal")
                else None
            )
            url = (
                f"{self.base_url}{relative_url}"
                if relative_url
                else "URL not available"
            )
            if self.link_convertor:
                url = self.link_convertor(url)
            # Price extraction
            price_span = div.find("span", class_="a-offscreen")
            price = (
                price_span.get_text().strip() if price_span else "Price not available"
            )

            # Rating extraction
            rating_span = div.find("span", class_="a-icon-alt")
            rating = float(rating_span.get_text().split()[0]) if rating_span else 0.0

            # Number of ratings extraction
            number_of_ratings_span = div.find("span", class_="a-size-base")
            number_of_ratings_text = (
                re.sub("[^0-9]", "", number_of_ratings_span.get_text())
                if number_of_ratings_span
                else "0"
            )
            number_of_ratings = (
                int(number_of_ratings_text) if number_of_ratings_text else 0
            )

            image_div = div.find("span", {"data-component-type": "s-product-image"})
            image_url = (
                image_div.find("img")["src"]
                if image_div and image_div.find("img")
                else "Image not available"
            )
            # ASIN extraction
            asin = div.get("data-asin", "ASIN not available")

            product = Product(
                title=title,
                url=url,
                price=price,
                rating=rating,
                number_of_ratings=str(number_of_ratings),
                asin=asin,
                image_url=image_url,
            )
            products_list.append(product)

        return products_list

    def search(
        self, keyword: str, num_results: int, sort_by: SortOptions = None, find_deals: bool = False
    ) -> List[Product]:
        """Searches for products and iterates through pages until it gathers the desired number of results."""
        all_products = []
        page_number = 1
        while len(all_products) < num_results:
            # Get the HTML content of the current page
            html_content = self.get_page_content(keyword, page_number, sort_by=sort_by, find_deals=find_deals)
            # Extract products from the current page
            page_products = self.extract_single_page_products(html_content)

            # Add extracted products to the all_products list
            all_products.extend(page_products)

            # Check if we have enough products, if not, move to the next page
            if len(page_products) < 48 or len(all_products) >= num_results:
                break  # Break if the last page is reached or we have enough results

            # Increment the page number to fetch the next page
            page_number += 1

        # Return the specified number of products
        return all_products[:num_results]

    def browse_amazon(self, link: str) -> str:
        html = self.client.send_request(link)
        soup = BeautifulSoup(html, "html.parser")
        content = soup.body
        markdown_content = html2text.HTML2Text().handle(str(content))
        return markdown_content

    def get_element_text_by_id(self, soup, element_id: str) -> str:
        """
        Returns an element by its ID using BeautifulSoup.

        :param html_content: The HTML content as a string.
        :param element_id: The ID of the element to search for.
        :return: The text content of the found element or None if no element is found.
        """
        element = soup.find(id=element_id)
        return element.get_text(strip=True) if element else ""
    
    def extract_amazon_rating(self, soup: str):
        reviews_container = soup.find(id="averageCustomerReviews")
        if reviews_container:
            rating_element = reviews_container.find('span', {'class': 'a-size-base a-color-base'})
            if rating_element:
                rating_text = rating_element.get_text(strip=True)
                try:
                    rating = float(rating_text)
                    return rating
                except ValueError:
                    return None
        return None

    def get_elem_by_id(self, soup, element_id: str):
        elem = soup.find(id=element_id)
        return elem

    def extract_first_number(self, text: str):
        """
        Extracts the first sequence of numbers from a given text.
        The number can have commas (e.g., 1,000).

        :param text: The text from which to extract the number.
        :return: The first number found in the text as a float, or None if no number is found.
        """
        # Search for a pattern that represents a number with optional commas
        match = re.search(r'(\d{1,3}(?:,\d{3})*(\.\d+)?)', text)
        if match:
            # Remove commas and convert to float
            number = float(match.group(1).replace(',', ''))
            return number
        else:
            return None

    def get_video_links_by_id(self, soup: str, container_id: str):
        """
        Returns a list of video links contained within a specific container ID.

        :param html_content: The HTML content as a string.
        :param container_id: The ID of the container element that includes video links.
        :return: A list of video links or an empty list if no links are found.
        """
        container = soup.find(id=container_id)
        video_links = []

        if container:
            video_tags = container.find_all("a")
            for video in video_tags:
                if video.get("href"):
                    if "vdp" in video["href"]:
                        video_links.append(video["href"])
               
        return video_links

    def get_product_details(self, product_link: str) -> DetailedProduct:
        html = self.client.send_request(product_link)
        soup = BeautifulSoup(html, "html.parser")

        try:
            title = self.get_element_text_by_id(soup, "productTitle")
        except Exception:
            title = ""

        try:
            rating = float(self.extract_amazon_rating(soup))
        except Exception:
            rating = 0.0  # Set a default value, you can choose any appropriate default

        try:
            number_of_reviews = float(
                self.extract_first_number(
                    self.get_element_text_by_id(soup, "acrCustomerReviewText")
                )
            )
        except Exception:
            number_of_reviews = 0.0  # Set a default value, you can choose any appropriate default

        try:
            description = self.get_element_text_by_id(soup, "productDescription")
        except Exception:
            description = ""

        try:
            product_image = self.get_elem_by_id(soup, "landingImage").get("src", "")
        except Exception:
            product_image = ""  # Set to None if not found

        try:
            product_information_string = html2text.HTML2Text().handle(
                self.get_element_text_by_id(soup, "centerCol")
            )
        except Exception:
            product_information_string = ""

        try:
            product_feature_string = html2text.HTML2Text().handle(
                self.get_element_text_by_id(soup, "aplus_feature_div")
            )
        except Exception:
            product_feature_string = ""

        try:
            seller_name = self.get_element_text_by_id(soup, "bylineInfo").replace("Visit the", "").strip()
        except Exception:
            seller_name = ""

        try:
            seller_link = self.get_elem_by_id(soup, "bylineInfo").get("href", "")
        except Exception:
            seller_link = ""

        try:
            video_urls = self.get_video_links_by_id(soup, "vse-cards-vw-dp")
        except Exception:
            video_urls = []
            
        try:
            price = soup.find(class_='priceToPay').get_text()
        except Exception:
            price = ""

        return DetailedProduct(
            title=title,
            price=price,
            rating=rating,
            number_of_reviews=number_of_reviews,
            description=description,
            product_image=product_image,
            product_information_string=product_information_string,
            product_feature_string=product_feature_string,
            seller_name=seller_name,
            seller_link=seller_link,
            video_urls=video_urls
        )

    # def __del__(self):
    #    self.stop_chrome()


if __name__ == "__main__":
    l = transform_to_affiliate_link(
        "https://www.amazon.com/Lasko-755320-Ceramic-Digital-Display/dp/B000TTV2QS?ref_=Oct_DLandingS_D_570974f5_1",
        "zain0694-20"
    )
    print(l)