from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build

class SubscriptionChecker:
    def __init__(self, credentials_path: str):
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/androidpublisher']
        )

    def check_subscription(self, package_name: str, token: str) -> dict:
        service = build('androidpublisher', 'v3', credentials=self.credentials)
        try:
            return service.purchases().subscriptionsv2().get(
                packageName=package_name,
                token=token
            ).execute()
        except Exception as e:
            raise ValueError(f"Failed to check subscription: {e}") from e

    def check_one_time_purchase(self, package_name: str, token: str) -> dict:
        service = build('androidpublisher', 'v3', credentials=self.credentials)
        try:
            return service.purchases().products().get(
                packageName=package_name,
                productId=token,
                token=token
            ).execute()
        except Exception as e:
            raise ValueError(f"Failed to check one-time purchase: {e}") from e


if __name__ == "__main__":
    c = SubscriptionChecker("/home/zain/Akalmand.ai/api/creds/academi-ai-6173d917c2a1.json")
    data = c.check_subscription("com.ainnovate.academiaii", "omdgjnaekifnijnfclobnhej.AO-J1OytfIjL9Unf7QOGGpWQX-OzoTP1PtrYZ8xJec5FLoPSp562JOm0Px-tdBrYWn3bWFJ8BrnPwMcTSwdCLPt8nBE6DY6AwF41vZzgccO5FcsW3T4X7qw")
    product_ids = [item['productId'] for item in data.get('lineItems', [])]
    print(product_ids)
