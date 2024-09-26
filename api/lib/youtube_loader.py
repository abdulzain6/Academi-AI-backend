from langchain.document_loaders.base import BaseLoader
from langchain.schema import Document
import requests

class YoutubeLoader(BaseLoader):
    def __init__(self, serverless_url: str, auth_key: str, video_url: str) -> None:
        self.serverless_url = serverless_url
        self.auth_key = auth_key
        self.video_url = video_url
    
    def load(self):
        headers = {
            'X-Require-Whisk-Auth': self.auth_key,
        }

        json_data = {
            'url': self.video_url,
        }

        response = requests.post(
            self.serverless_url,
            headers=headers,
            json=json_data
        )
        response.raise_for_status()
        
        return [Document(page_content=response.text)]
    