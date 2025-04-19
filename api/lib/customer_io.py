import logging
import requests
import json
from typing import Optional, Dict, Any

class CustomerIOClient:
    def __init__(self, site_id: str, api_key: str) -> None:
        self.site_id: str = site_id
        self.api_key: str = api_key
        self.base_url: str = "https://track.customer.io/api/v1"

    def send_event(
        self, 
        customer_id: str, 
        event_name: str, 
        event_data: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """
        Sends a custom event to Customer.io with optional event data.
        """
        
        url: str = f"{self.base_url}/customers/{customer_id}/events"
        payload: Dict[str, Any] = {
            "name": event_name,
            "data": event_data or {}
        }
        logging.info(f"Sending event {event_name} to customer {customer_id} with data {event_data}")
        response: requests.Response = requests.post(
            url,
            auth=(self.site_id, self.api_key),
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=5
        )
        return response

    def create_or_update_customer(
        self, 
        customer_id: str, 
        attributes: Dict[str, Any]
    ) -> requests.Response:
        """
        Creates or updates a Customer.io customer with the given attributes.
        """
        logging.info(f"Creating or updating customer {customer_id} with attributes {attributes}")
        url: str = f"{self.base_url}/customers/{customer_id}"
        response: requests.Response = requests.put(
            url,
            auth=(self.site_id, self.api_key),
            headers={"Content-Type": "application/json"},
            data=json.dumps(attributes)
        )
        return response


if __name__ == "__main__":
    client = CustomerIOClient("", "")
    cust = client.create_or_update_customer("test-id-new", {"email": "zain@typicl.ai"})
    print(cust.text)
    resp = client.send_event(
        "test-id-new",
        "user_signed_up",
        {
            "email": "abdulzain6@gmail.com",
            "first_name": "Abdulzain",
            
        }
    )
    print(resp.text)
