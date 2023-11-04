import requests
import os


headers = {
    'accept': 'application/json',
    'Authorization': f'Bearer {os.getenv("APIKEY","ABRACADABRA_KAZAMM_HEHE_@#$")}',
}

response = requests.get(f'http://{os.getenv("URL", "api.academiai.org")}/api/v1/subscriptions-info/reset', headers=headers)
print(response.status_code)