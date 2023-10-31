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


