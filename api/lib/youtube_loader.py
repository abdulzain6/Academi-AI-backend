import logging
import time
import requests
from langchain.document_loaders.base import BaseLoader
from langchain.schema import Document

logging.basicConfig(level=logging.DEBUG)

class YoutubeLoader(BaseLoader):
    def __init__(self, serverless_url: str, auth_key: str, video_url: str, get_result_url: str) -> None:
        self.serverless_url = serverless_url
        self.auth_key = auth_key
        self.video_url = video_url
        self.get_result_url = get_result_url
        
    def load(self):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Basic {self.auth_key}',
        }

        params = {
            'blocking': 'false',
        }
        json_data = {
            'url': self.video_url,
        }

        response = requests.post(
            self.serverless_url,
            params=params,
            headers=headers,
            json=json_data
        )
        response.raise_for_status()
        activation_id = response.json()["activationId"]
        logging.info(f"FUnction invoke started: {response.text}")
        for _ in range(24):
            response = requests.get(
                f'{self.get_result_url}{activation_id}',
                headers=headers,
            ).json()
            logging.info(f"Polling... {response}")
                            
            
            if response.get("response", {}).get("result"):
                if response["response"]["result"].get("statusCode") == 500:
                    raise RuntimeError("Unable to transcribe video")
                return [Document(page_content=response["response"]["result"]["body"])]
            
            time.sleep(5)
            
        raise RuntimeError("Tiemout")
    
    
if __name__ == "__main__":
    loader = YoutubeLoader(
        serverless_url="https://faas-blr1-8177d592.doserverless.co/api/v1/namespaces/fn-e4125fdf-f695-4a9e-9bc4-75db4a5994db/actions/academi/yt_transcript",
        auth_key="N2FlOWIwMjAtOGY4Ny00NGE4LThiMzEtMmJlMGZiMDUwYjk1OmtqNzd6R0xMNWo4YjNoZklUMmJOekkwbFVBcDIzSVpmbWJ5ZElSZGEzWDdhVm1TTmQ4WDFiZlJ6SU81dnkyRk0=",
        video_url="https://youtu.be/ShsUfAMQ3iQ?si=88WK_s_c-pQAy4R3",
        get_result_url="https://faas-blr1-8177d592.doserverless.co/api/v1/namespaces/fn-e4125fdf-f695-4a9e-9bc4-75db4a5994db/activations/"
    )
    print(loader.load())