import requests
from typing import Optional, Dict, Any

class CycleTlsServerClient:
    def __init__(self, server_url: str, default_args: Optional[Dict[str, Any]] = None, proxy: Optional[str] = None):
        self.server_url = server_url
        if not default_args:
            self.default_args = {
                "body": "",
                "ja3": "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,17513-11-45-23-27-51-5-18-10-65037-13-43-35-16-65281-0,29-23-24,0",
                "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                "headers": {
                    'authority': 'www.udemy.com',
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'accept-language': 'en-US,en;q=0.9',
                    'cache-control': 'max-age=0',
                    'dnt': '1',
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Linux"',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'none',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                },
                "proxy": proxy
            }
        else:
            self.default_args = default_args

    def _send_request(self, method: str, url: str, use_proxy: bool = False, **kwargs):
        # Merge default arguments with the provided ones
        args = self.default_args.copy()
        args.update(kwargs)
        if not use_proxy:
            args.pop("proxy")
        response = requests.post(
            self.server_url, json={"args": args, "url": url, "method": method}
        )
        return response

    def get(self, url: str, **kwargs):
        return self._send_request('get', url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._send_request('post', url, **kwargs)

    def put(self, url: str, **kwargs):
        return self._send_request('put', url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._send_request('delete', url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self._send_request('patch', url, **kwargs)

    def head(self, url: str, **kwargs):
        return self._send_request('head', url, **kwargs)

    def options(self, url: str, **kwargs):
        return self._send_request('options', url, **kwargs)

if __name__ == '__main__':
    client = CycleTlsServerClient(server_url="http://localhost:3000/fetch", proxy="http://dprulefr-rotate:7obapq1qv8fl@p.webshare.io:80")
    response_get = client.get(
        "https://www.udemy.com/course/javascript-and-php-programming-complete-course/?couponCode=FB2C7B9E6EC0F944BBDB",
        use_proxy=True
    )
    print("4551820" in response_get.text)
    response_post = client.post("https://www.udemy.com/api-2.0/course-landing-components/5909998/me/?couponCode=325A32EE01840618BC62&utm_source=aff-campaign&utm_medium=udemyads&components=redeem_coupon,price_text")
    print(response_post.text)
