import requests

cookies = {
    'ezoictest': 'stable',
    'ezoab_84493': 'mod112',
    'ezoadgid_84493': '-1',
    'ezosuibasgeneris-1': '551d2f28-a1af-4692-7d53-a2c582bc79d4',
    'lp_84493': 'https://couponscorpion.com/',
    'ezovuuid_84493': 'bce832a2-5e5b-4bae-55f1-2a9ad0670cfc',
    'ezoref_84493': 'google.com',
    'ezds': 'ffid%3D1%2Cw%3D1280%2Ch%3D720',
    'ezohw': 'w%3D1280%2Ch%3D603',
    '_sharedid': '8b104117-fe20-4ae8-97c2-907a2c569570',
    '_sharedid_cst': 'zix7LPQsHA%3D%3D',
    '_cc_id': '2137e714a86772595c284c8f8f1d6f20',
    'panoramaIdType': 'panoDevice',
    '_au_1d': 'AU1D-0100-001718824763-B77EV09W-5VH0',
    '_gid': 'GA1.2.1579778029.1718824765',
    'pbjs-unifiedid': '%7B%22TDID%22%3A%2204b3d230-369b-46c6-a869-d0d8ea1faab0%22%2C%22TDID_LOOKUP%22%3A%22TRUE%22%2C%22TDID_CREATED_AT%22%3A%222024-05-19T19%3A19%3A26%22%7D',
    'pbjs-unifiedid_cst': 'zix7LPQsHA%3D%3D',
    'panoramaId_expiry': '1718911167307',
    'cto_bidid': 'g8_ayF9UYWl3eGxoZlpKTGxFRzhhUXBBTWt1WktKRUZUUWpHVlBhdnZwUXZJNHdEcUpJU1pMbFZZWHYlMkZyR2g3MDU0S29OcGtFQWM5TmtTUHFtOHNxbERQNzNSdTZkcnNPZ2tCVVF3RHpIcDl2bU1qU1RWd3V6ZGJwZkxDRiUyQjg3V0JPbWs',
    'ezux_ifep_84493': 'true',
    'ezux_lpl_84493': '1718824795560|58320732-467c-47cd-6768-c2fa2b63c976|false',
    'ezvignetteviewed': 'true',
    '__qca': 'P0-1765030975-1718824801523',
    '_ga_FVWZ0RM4DH': 'GS1.1.1718824802.1.0.1718824802.60.0.0',
    'active_template::84493': 'pub_site.1718824802',
    'ezopvc_84493': '2',
    'ezovuuidtime_84493': '1718824803',
    'cs': 'ro',
    '_ga': 'GA1.2.978464713.1718824760',
    'cto_bundle': 'oKeMnV9FSG1IdHVQYnBaVGRxJTJGTFl0aEswSmtjSklMZ2hEZGpyQ2hialdnU3ltZzBScUg5VUY1ZHFnT0o4dUxUV0xHY1FUekVlSkwlMkZmTHpuYU5FdUdFRTZlNDdOU0MlMkZMc0hZYVElMkZhR3l3eGJ6aU4lMkYybDJEdEVIamk3TXVCb3ZwWjhMdGt4YWIwdkZ2cXoyRXNYdThUREdkVFRhNmhZWEl2Y0N3V1NFZnVYOUlWWHlZJTNE',
    '_ga_48DHEEN9NC': 'GS1.1.1718824759.1.1.1718825042.0.0.0',
    '__gads': 'ID=0d82fa0f391e55ed:T=1718824762:RT=1718825074:S=ALNI_Ma5LOh5bqzIUg1FwASReABGQDF1cg',
    '__gpi': 'UID=00000e4e7ddba26e:T=1718824762:RT=1718825074:S=ALNI_MY6Je0ka_-dqNj3jJfUfV45WR6VMg',
    '__eoi': 'ID=1e72bd7a86877940:T=1718824762:RT=1718825074:S=AA-Afja5ztwGmGTKcKCN8nZe1OJ1',
    'ezux_et_84493': '194',
    'ezux_tos_84493': '511',
}

headers = {
    'authority': 'couponscorpion.com',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    # 'cookie': 'ezoictest=stable; ezoab_84493=mod112; ezoadgid_84493=-1; ezosuibasgeneris-1=551d2f28-a1af-4692-7d53-a2c582bc79d4; lp_84493=https://couponscorpion.com/; ezovuuid_84493=bce832a2-5e5b-4bae-55f1-2a9ad0670cfc; ezoref_84493=google.com; ezds=ffid%3D1%2Cw%3D1280%2Ch%3D720; ezohw=w%3D1280%2Ch%3D603; _sharedid=8b104117-fe20-4ae8-97c2-907a2c569570; _sharedid_cst=zix7LPQsHA%3D%3D; _cc_id=2137e714a86772595c284c8f8f1d6f20; panoramaIdType=panoDevice; _au_1d=AU1D-0100-001718824763-B77EV09W-5VH0; _gid=GA1.2.1579778029.1718824765; pbjs-unifiedid=%7B%22TDID%22%3A%2204b3d230-369b-46c6-a869-d0d8ea1faab0%22%2C%22TDID_LOOKUP%22%3A%22TRUE%22%2C%22TDID_CREATED_AT%22%3A%222024-05-19T19%3A19%3A26%22%7D; pbjs-unifiedid_cst=zix7LPQsHA%3D%3D; panoramaId_expiry=1718911167307; cto_bidid=g8_ayF9UYWl3eGxoZlpKTGxFRzhhUXBBTWt1WktKRUZUUWpHVlBhdnZwUXZJNHdEcUpJU1pMbFZZWHYlMkZyR2g3MDU0S29OcGtFQWM5TmtTUHFtOHNxbERQNzNSdTZkcnNPZ2tCVVF3RHpIcDl2bU1qU1RWd3V6ZGJwZkxDRiUyQjg3V0JPbWs; ezux_ifep_84493=true; ezux_lpl_84493=1718824795560|58320732-467c-47cd-6768-c2fa2b63c976|false; ezvignetteviewed=true; __qca=P0-1765030975-1718824801523; _ga_FVWZ0RM4DH=GS1.1.1718824802.1.0.1718824802.60.0.0; active_template::84493=pub_site.1718824802; ezopvc_84493=2; ezovuuidtime_84493=1718824803; cs=ro; _ga=GA1.2.978464713.1718824760; cto_bundle=oKeMnV9FSG1IdHVQYnBaVGRxJTJGTFl0aEswSmtjSklMZ2hEZGpyQ2hialdnU3ltZzBScUg5VUY1ZHFnT0o4dUxUV0xHY1FUekVlSkwlMkZmTHpuYU5FdUdFRTZlNDdOU0MlMkZMc0hZYVElMkZhR3l3eGJ6aU4lMkYybDJEdEVIamk3TXVCb3ZwWjhMdGt4YWIwdkZ2cXoyRXNYdThUREdkVFRhNmhZWEl2Y0N3V1NFZnVYOUlWWHlZJTNE; _ga_48DHEEN9NC=GS1.1.1718824759.1.1.1718825042.0.0.0; __gads=ID=0d82fa0f391e55ed:T=1718824762:RT=1718825074:S=ALNI_Ma5LOh5bqzIUg1FwASReABGQDF1cg; __gpi=UID=00000e4e7ddba26e:T=1718824762:RT=1718825074:S=ALNI_MY6Je0ka_-dqNj3jJfUfV45WR6VMg; __eoi=ID=1e72bd7a86877940:T=1718824762:RT=1718825074:S=AA-Afja5ztwGmGTKcKCN8nZe1OJ1; ezux_et_84493=194; ezux_tos_84493=511',
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

params = {
    'go': 'Q25aTzVXS1l0TXg1TExNZHE5a3pESW9pbWxQeklCT0x5YWxEZ0srenAxd1JUaFEzMUs4emRNeFhmNERGZG45YTVUTUYvMDNYelBPNWR4d0ZpK3FaNXFZQjZDUzlJLzNrN3JIY1ZVUzJKajZlSElvWmZCME5LWkN2a3FiWEFaODBvcC9GbS85VzU5dTRmR1JPT2l0aVRnPT0=',
    's': '599310f4b681404d03fbb5c9b3aaa323c2c445d7',
    'n': '1675181666',
    'a': '0',
}

response = requests.get('https://couponscorpion.com/scripts/udemy/out.php', params=params, cookies=cookies, headers=headers )

print(response.status_code)