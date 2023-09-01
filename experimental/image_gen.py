from typing import Optional, Dict
from urllib.parse import urlparse
import os
import requests
from PIL import Image
from io import BytesIO

from typing import Optional, Dict, List
from urllib.parse import urlparse
import os
import requests
from PIL import Image
from io import BytesIO

class PexelsImageSearch:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.used_images: List[str] = []

    def get_extension_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        root, ext = os.path.splitext(parsed.path)
        return ext

    def search_images(self, query: str, target_width: int, target_height: int, per_page: int = 15) -> Optional[Dict]:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page={per_page}"
        headers = {"Authorization": self.api_key}
        response = requests.get(url, headers=headers)
        data = response.json()
        if photos := data.get('photos', []):
            for photo in sorted(
                photos,
                key=lambda x: abs(x['width'] - target_width) + abs(x['height'] - target_height),
            ):
                if photo['src']['original'] not in self.used_images:
                    self.used_images.append(photo['src']['original'])
                    return photo
        return None

    def download_and_resize_image(self, image_url: str, target_width: int, target_height: int, output_path: str) -> None:
        response = requests.get(image_url)
        img_data = BytesIO(response.content)
        with Image.open(img_data) as img:
            img = img.resize((target_width, target_height), Image.LANCZOS)
            ext = self.get_extension_from_url(image_url)
            img.save(f"{output_path}{ext}")

    def search_download_and_resize(self, query: str, target_width: int, target_height: int, output_path: str, per_page: int = 15) -> None:
        if closest_image := self.search_images(query, target_width, target_height, per_page):
            image_url = closest_image['src']['original']
            self.download_and_resize_image(image_url, target_width, target_height, output_path)
        else:
            print("No suitable image found.")
            
