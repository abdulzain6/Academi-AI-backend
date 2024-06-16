import requests

class CycleTlsServerClient:
    def __init__(self, server_url: str, default_args: dict = None, proxy: str = None):
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
                    # 'cookie': '__udmy_2_v57r=2e4109b0c498429680f7228523b27889; csrftoken=ErrmqtIkUnfvL46vRfv7OXlbbnXvwcelFGsdRSN6ktgQaEfcQKi1swCzKXN5aDSx; ud_cache_brand=PKen_US; ud_cache_campaign_code=""; ud_cache_marketplace_country=PK; ud_cache_price_country=PK; ud_cache_release=18455cedd3bda1a8c5f7; ud_cache_user=""; ud_cache_version=1; ud_cache_language=en; ud_cache_device=None; ud_cache_logged_in=0; __cfruid=af3bf3e10a6cfede54cdedede3c3e5c516450a2c-1718543675; cf_clearance=8Qaq0pET_ms1BuHoiK4KiZeO8KityWhI7WAjF19LucI-1718543679-1.0.1.1-8onJ9U0dvodLJPyZ2w8a2xYqFmEYp5BTpliFRjs.3MVEQYLYr71A599ggcWCKOylpgIiiFdQhY8DFGvyBLknMQ; ud_firstvisit=2024-06-16T13:14:40.322111+00:00:1sIpiS:2LXuHT9n-XKrr1HlhYpszTo0FxU; _gid=GA1.2.1609284272.1718543683; __ssid=c6bc65b55bb3aee0605b33c5f887962; _gcl_au=1.1.298924902.1718543684; blisspoint_fpc=d6c3f9c8-9a4e-4f07-b5c8-14240839e6b3; _yjsu_yjad=1718543684.7026406e-b717-4e5c-aa43-4962740be575; _fbp=fb.1.1718543684684.32687731461124009; __stripe_mid=1cddcad4-1d41-4b5e-8116-14160c614ab01e2abe; FPAU=1.1.298924902.1718543684; _ga=GA1.2.2133943494.1718543683; _ga_7YMFEFLR6Q=GS1.1.1718543684.1.1.1718547591.0.0.0; OptanonConsent=isGpcEnabled=0&datestamp=Sun+Jun+16+2024+19%3A20%3A01+GMT%2B0500+(Pakistan+Standard+Time)&version=202402.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=4b10f411-ac5b-4616-9374-d5661d8b2d41&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0003%3A1%2CC0005%3A0%2CC0004%3A0%2CC0001%3A1%2CC0002%3A1&AwaitingReconsent=false; _rdt_uuid=1718543684388.6cf132aa-2c04-4e37-995d-6689ad8da7c9; ki_t=1718543819747%3B1718543819747%3B1718547604547%3B1%3B6; evi="3@jPsdACXyzhng1CEF3VbhArxN1W4UbcdUA426NUHHOsM07b6Gimw2cXJG"; exaff=%7B%22start_date%22%3A%222024-06-16T13%3A14%3A34.434322Z%22%2C%22code%22%3A%22bnwWbXPyqPU-rrr89iWFh1uAzU8z7QXJ6Q%22%2C%22merchant_id%22%3A47901%2C%22aff_type%22%3A%22LS%22%2C%22aff_id%22%3A40046%7D:1sIs4H:-2-6iNFbgCaaM2w11P94-papTUY; ud_rule_vars=eJx1jtFuAiEQRX_F8NpqhmHYBb5lE8Iiq0RbUpj1xfjvJVGbJq2vN_fcc6-CQz0kTnt_yS1zqQ4TSbAzRLKG0A4GlhHRaFQzjsZYF0s55STcRlwnseTa-M76feA09XwSCEhbGLZy2EjlJDlFO1Jay-ENwAFM4r23zqGjXNZ49FzDsuToW1lrTP4Sag7z-bGWPxvXNfZzv7jYmy09zJw__jFrR9qh3I1gidQfc01fa2qvbv_AaK2lJ3wTt29WO1py:1sIs4H:krXsSB6RElGXVhfi_AIykPBiR4E; __cf_bm=S.EO50OUaqMXhcplbOOoCE0vSUZQg.OYWe14TaXfTDE-1718552721-1.0.1.1-AVxqs18JnC0o6G24NJaIDdw.bkKr5bnPvxG4xK73xfNhZ8owuBkHFCARka0Tfw4o95dB3isoqtb8M3cFf6zxAg',
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

    def send_request(self, get_url: str):
        response = requests.post(
            self.server_url, json={"args": self.default_args, "url": get_url}
        )
        return response
    
    
client = CycleTlsServerClient(server_url="http://localhost:3000/fetch")
print("4551820" in client.send_request("https://www.udemy.com/course/javascript-and-php-programming-complete-course/?couponCode=FB2C7B9E6EC0F944BBDB").text)
print(client.send_request("https://www.udemy.com/api-2.0/course-landing-components/5909998/me/?couponCode=325A32EE01840618BC62&utm_source=aff-campaign&utm_medium=udemyads&components=redeem_coupon,price_text").text)