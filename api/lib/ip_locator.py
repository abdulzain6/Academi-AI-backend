import requests
from requests.exceptions import RequestException
from typing import Optional, Dict


class IPLocator:
    API_ENDPOINTS = [
        "https://ipwhois.app/json/{}",
        "https://ipapi.com/ip_api.php?ip={}",
        "http://ip-api.com/json/{}",
        "https://ipapi.co/{}/json/",
        "https://ipinfo.io/{}/json",
        "https://freegeoip.app/json/{}",
    ]

    def __init__(self):
        self.api_counter = 0

    def get_location_from_ip(self, ip: str) -> Optional[Dict[str, str]]:
        for _ in range(len(self.API_ENDPOINTS)):
            try:
                url = self.API_ENDPOINTS[self.api_counter].format(ip)
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                data = response.json()
                return self._parse_response(url, data)
            except RequestException as e:
                print(f"Error with {url}: {str(e)}")
            except (KeyError, ValueError) as e:
                print(f"Error parsing data from {url}: {str(e)}")
            except Exception as e:
                print(f"Unexpected error with {url}: {str(e)}")
            finally:
                self.api_counter = (self.api_counter + 1) % len(self.API_ENDPOINTS)

        print("All APIs failed to retrieve location data")
        return None

    def _parse_response(self, url: str, data: Dict) -> Dict[str, str]:
        if "ipapi.co" in url or "freegeoip.app" in url or "ipapi.com" in url:
            return {
                'city': data.get('city'),
                'country': data.get('country_name')
            }
        elif "ipinfo.io" in url or "ip-api.com" in url or "ipwhois.app" in url:
            return {
                'city': data.get('city'),
                'country': data.get('country')
            }
        elif "geo.ipify.org" in url:
            return {
                'city': data.get('location', {}).get('city'),
                'country': data.get('location', {}).get('country')
            }
        elif "ipstack.com" in url or "ipdata.co" in url:
            return {
                'city': data.get('city'),
                'country': data.get('country_name')
            }
        else:
            raise ValueError("Unknown API endpoint")