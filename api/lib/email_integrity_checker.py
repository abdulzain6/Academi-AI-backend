import requests
import re

class EmailIntegrityChecker:
    def __init__(self):
        self.disposable_domains = self.download_and_parse_lists()

    @staticmethod
    def download_and_parse_lists() -> set:
        urls = [
            "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf",
            "https://github.com/disposable/disposable/blob/master/blacklist.txt",
            "https://github.com/ivolo/disposable-email-domains/blob/master/wildcard.json",
            "https://gist.githubusercontent.com/abdulzain6/a732b12453f1bc5b62a9897c6b56a793/raw/31db814f9ed99a70610f1c268a9e04a8c5669fd8/disposable-email-provider-domains"
        ]

        domains = set()
        for url in urls:
            try:
                response = requests.get(url)
                response.raise_for_status()  # Raise an error for bad status codes
                if url.endswith('.json'):
                    data = response.json()
                    domains.update(data)
                else:
                    lines = response.text.splitlines()
                    domains.update(filter(EmailIntegrityChecker.is_valid_domain, lines))
            except Exception as e:
                print(f"Error downloading or parsing data from {url}: {e}")

        return domains

    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        # Simple regex to check if a string looks like a domain
        return re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain) is not None

    def is_valid_email(self, email: str) -> bool:
        domain = email.split('@')[-1]
        return domain not in self.disposable_domains and self.is_valid_domain(domain)
