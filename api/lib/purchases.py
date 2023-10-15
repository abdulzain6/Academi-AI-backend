from google.oauth2 import service_account
from google.auth.transport.requests import Request
from typing import Optional
import requests
import redis


class SubscriptionChecker:
    def __init__(self, service_account_file_path: str, redis_host: str, redis_port: int):
        self.service_account_file_path = service_account_file_path
        self.credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file_path,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        self.redis_client = redis.Redis(host=redis_host, port=redis_port)

    def fetch_token(self) -> Optional[str]:
        if self.credentials.expired:
            self.credentials.refresh(Request())
        return self.credentials.token

    def cache_subscription_status(self, user_id: str, status: bool) -> None:
        self.redis_client.setex(user_id, 3600, int(status))

    def get_cached_subscription_status(self, user_id: str) -> Optional[bool]:
        cached_status = self.redis_client.get(user_id)
        return bool(int(cached_status)) if cached_status is not None else None

    def check_subscription_via_google_play(
        self, user_id: str, token: str, package_name: str, product_id: str
    ) -> Optional[bool]:
        # First, check the cache
        cached_status = self.get_cached_subscription_status(user_id)
        if cached_status is not None:
            return cached_status

        # Fetch new access token if needed
        access_token = self.fetch_token()
        if access_token is None:
            print("Failed to fetch access token")
            return None

        url = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/purchases/subscriptions/{product_id}/tokens/{token}"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            purchase_info = response.json()
            is_subscribed = purchase_info.get("autoRenewing", False)
            self.cache_subscription_status(user_id, is_subscribed)  # Cache the new status
            return is_subscribed
        else:
            print(f"Failed to verify subscription: {response.content}")
            return None


# Example usage
checker = SubscriptionChecker("/home/zain/Akalmand.ai/api/creds/academi-ai-0b2b2076a3eb.json", "localhost", 6379)
is_subscribed = checker.check_subscription_via_google_play("user_id_here", "token_here", "package_name_here", "product_id_here")
