import time, os
import requests


class RunpodCaller:
    def __init__(self, base_url: str, endpoint_id: str, token: str = None) -> None:
        if token is None:
            token  = os.getenv("RUNPOD_TOKEN")
            
        self.token = token
        self.base_url = base_url
        self.endpoint_id = endpoint_id
        

    def generate(self, input_data: dict):
        url = f"{self.base_url}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
        print("Request sent", url)
        
        print({"input": input_data})
        
        response = requests.post(url, json={"input": input_data}, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'output' in data:
            return data['output']
        
        if "error" in data:
            raise ValueError(f"Error, Try again later. Detail: {data['error']}")

            
        elif data.get('status') in ['IN_PROGRESS', 'IN_QUEUE']:
            status_url = f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{data['id']}"
            while True:
                status_response = requests.get(status_url, headers=headers, timeout=1000)
                print(f"Poll response, {status_response.text}")
                status_data = status_response.json()
                if status_data.get('status') == 'COMPLETED':
                    return status_data["output"]
                elif status_data.get('status') not in ['IN_QUEUE', 'IN_PROGRESS']:
                    raise ValueError(f"Error, Try again later.")
                time.sleep(1)  

        else:
            raise ValueError(f"Error, Try again later. Detail: {data}")