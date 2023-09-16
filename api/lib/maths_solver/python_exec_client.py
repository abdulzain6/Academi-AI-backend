import httpx
from pydantic import BaseModel




class Urls(BaseModel):
    main_url: str
    evaluate_url: str
    available_libraries_url: str

class PythonClient:
    def __init__(self, urls: Urls, timeout: int) -> None:
        self.urls = urls
        self.timeout = timeout
        
    def evaluate_code(self, code: str):
        try:
            json_data = {
                'code': code,
                'timeout': self.timeout,
            }
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
            }
            response = httpx.post(self.urls.evaluate_url, headers=headers, json=json_data, timeout=httpx.Timeout(self.timeout))
            return response.json()
        except Exception as e:
            return {"error" : str(e)}

    def get_available_libraries(self):
        try:
            return httpx.get(self.urls.available_libraries_url, timeout=httpx.Timeout(self.timeout)).json()
        except Exception as e:
            return {"error" : str(e)}        

        


