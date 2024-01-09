import requests

class MermaidClient:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url

    def get_diagram_image(self, diagram_code: str, image_type: str = 'svg') -> bytes:
        headers = {'Content-Type': 'text/plain'}
        response = requests.post(f"{self.server_url}/generate?type={image_type}", data=diagram_code, headers=headers)
        response.raise_for_status()
        return response.content