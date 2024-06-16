import requests
from urllib.parse import urlparse, parse_qs, unquote
from bs4 import BeautifulSoup
import json

def validate_link_and_get_price(url: str) -> tuple[bool, float, float, str]:
    def make_url(url: str, id: int) -> str:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        coupon_code = query_params.get("couponCode", ["FREE"])[0]
        api_url = (f"https://www.udemy.com/api-2.0/course-landing-components/{id}/me/"
                   f"?couponCode={coupon_code}&utm_source=aff-campaign&utm_medium=udemyads&components=redeem_coupon,price_text")
        return unquote(api_url)

    headers = {
        'authority': 'www.udemy.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'cookie': '__udmy_2_v57r=2e4109b0c498429680f7228523b27889; csrftoken=ErrmqtIkUnfvL46vRfv7OXlbbnXvwcelFGsdRSN6ktgQaEfcQKi1swCzKXN5aDSx; ud_cache_brand=PKen_US; ud_cache_campaign_code=""; ud_cache_marketplace_country=PK; ud_cache_price_country=PK; ud_cache_release=18455cedd3bda1a8c5f7; ud_cache_user=""; ud_cache_version=1; ud_cache_language=en; ud_cache_device=None; ud_cache_logged_in=0; __cfruid=af3bf3e10a6cfede54cdedede3c3e5c516450a2c-1718543675; cf_clearance=8Qaq0pET_ms1BuHoiK4KiZeO8KityWhI7WAjF19LucI-1718543679-1.0.1.1-8onJ9U0dvodLJPyZ2w8a2xYqFmEYp5BTpliFRjs.3MVEQYLYr71A599ggcWCKOylpgIiiFdQhY8DFGvyBLknMQ; ud_firstvisit=2024-06-16T13:14:40.322111+00:00:1sIpiS:2LXuHT9n-XKrr1HlhYpszTo0FxU; _gid=GA1.2.1609284272.1718543683; __ssid=c6bc65b55bb3aee0605b33c5f887962; _gcl_au=1.1.298924902.1718543684; blisspoint_fpc=d6c3f9c8-9a4e-4f07-b5c8-14240839e6b3; _yjsu_yjad=1718543684.7026406e-b717-4e5c-aa43-4962740be575; _fbp=fb.1.1718543684684.32687731461124009; __stripe_mid=1cddcad4-1d41-4b5e-8116-14160c614ab01e2abe; __stripe_sid=81e3ae61-51f1-44f5-97ce-2f276af58fd41b7f54; FPAU=1.1.298924902.1718543684; __cf_bm=HrSEM4EhBjrazRnttA3uA9KgTWjNLA6RLNkVRQAw8fI-1718546798-1.0.1.1-gpCvyqr0pGy7OB9YHAauBzIrapbRjLZywMvL3pzySgXbkeDFM5TdeZEiTPam.e2ndpVr_yUGVvEBPO_614R41A; ki_t=1718543819747%3B1718543819747%3B1718547519240%3B1%3B5; _rdt_uuid=1718543684388.6cf132aa-2c04-4e37-995d-6689ad8da7c9; _ga=GA1.2.2133943494.1718543683; _ga_7YMFEFLR6Q=GS1.1.1718543684.1.1.1718547591.0.0.0; OptanonConsent=isGpcEnabled=0&datestamp=Sun+Jun+16+2024+19%3A19%3A53+GMT%2B0500+(Pakistan+Standard+Time)&version=202402.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=4b10f411-ac5b-4616-9374-d5661d8b2d41&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0003%3A1%2CC0005%3A0%2CC0004%3A0%2CC0001%3A1%2CC0002%3A1&AwaitingReconsent=false; _gat=1; exaff=%7B%22start_date%22%3A%222024-06-16T13%3A14%3A34.434322Z%22%2C%22code%22%3A%22bnwWbXPyqPU-rrr89iWFh1uAzU8z7QXJ6Q%22%2C%22merchant_id%22%3A47901%2C%22aff_type%22%3A%22LS%22%2C%22aff_id%22%3A40046%7D:1sIqjb:-qGjl4FE8IsmVg1MdQnjZv2MjNM; evi="3@WCrqltuRt-HQrUO0zbCcXRByeR-HDXF98FSd-VN3hePluGDS8V3tU2Zm"; eventing_session_id=NDJmYzJjZTAtYWMxOS00OG-1718549395737; ud_rule_vars="eJx1jtFqAyEQRX8l-NpmGXU06rcsiGtmW2laqc7mJeTfKySBQNvXyz333Ivg1N6I6RjPpReuLShCCX6BjN6h8tbBelDKGaUXdXDOh1zrRyERduIyi7W0zjc2HhPTPPJZKFC4B7uXdid1kBg0TqiNkfYFIADM4nW0TmmgXLf8HrmldS059rq1TPGcWknL6b5Wvjq3LY9zT1wezU53M5fPP8wYpA8GJ_DSovllbvS9Uf_v9g02k9VOg37AV3H9AVcQWmw=:1sIqjb:6hw3vkv6CG6tMzgdEaXGJ0x2_YM"; _dd_s=rum=0&expire=1718548496632',
        'dnt': '1',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    try:
        response = requests.get(url, headers=headers, allow_redirects=True)
        if response.status_code in (301, 302) or "is no longer available" in response.text or "no longer" in response.text:
            return False, 0.0, 0.0, ""
        
        soup = BeautifulSoup(response.text, "html.parser")
        course_id = soup.find("body").get("data-clp-course-id")
        print(soup.prettify())
        if course_id is None:
            raise ValueError("Course ID not found in the response")

        response = requests.get(make_url(url, int(course_id)), headers=headers)
        if "The coupon code entered" in response.text or "This coupon has exceeded its maximum possible redemptions and can no longer be used" in response.text:
            return False, 0.0, 0.0, ""

        data = json.loads(response.text)
        price_data = data["price_text"]["data"]["pricing_result"]
        sale_price = price_data["price"]["amount"]
        actual_price = price_data["list_price"]["amount"]
        end_date = price_data["campaign"]["end_time"]

        return True, sale_price, actual_price, end_date

    except Exception as e:
        print(e)
        return False, 0.0, 0.0, ""

# Example usage:
url = "https://www.udemy.com/course/javascript-and-php-programming-complete-course/?couponCode=FB2C7B9E6EC0F944BBDB"
result = validate_link_and_get_price(url)
print(result)  # Output: (True, sale_price, actual_price, end_date)
