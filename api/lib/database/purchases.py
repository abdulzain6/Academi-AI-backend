from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from pymongo import MongoClient
from enum import Enum
from typing import Dict, List, Optional, Tuple
from .points import UserPointsManager
from typing import Union
from bson.json_util import dumps, loads
from .cache_manager import CacheProtocol
import logging

class FeatureValueResponse(BaseModel):
    name: str
    main_data: Union[str, int]
    limit: Union[int, None]  # Included if relevant
    fallback_value: Union[str, None]  # Included if relevant


class SubscriptionType(str, Enum):
    FREE = "FREE"
    LITE = "LITE"
    PRO = "PRO"
    ELITE = "ELITE"


class SubscriptionProvider(str, Enum):
    PLAYSTORE = "PlayStore"
    APPSTORE = "AppStore"


class IncrementalFeature(BaseModel):
    name: str
    limit: int


class StaticFeature(BaseModel):
    name: str
    value: str | int


class MonthlyLimitFeature(BaseModel):
    name: str
    limit: int
    value: str
    fallback_value: str
    enabled: bool

class MonthlyCoinsFeature(BaseModel):
    name: str = "monthly_coins"
    amount: int

class SubscriptionFeatures(BaseModel):
    incremental: List[IncrementalFeature] = []
    static: List[StaticFeature] = []
    monthly_limit: List[MonthlyLimitFeature] = []
    monthly_coins: MonthlyCoinsFeature

logging.basicConfig(level=logging.INFO)

    
class SubscriptionManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        user_points_manager: UserPointsManager,
        plan_features: Dict[SubscriptionType, SubscriptionFeatures],
        cache_manager: CacheProtocol

    ):
        if any(sub_type not in plan_features for sub_type in SubscriptionType):
            raise ValueError(
                "All SubscriptionTypes must be specified in plan_features."
            )

        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.subscriptions = self.db["subscriptions"]
        self.old_tokens_subscription = self.db["old_tokens"]
        self.old_tokens_ontime = self.db["one_time"]
        self.subscriptions.create_index("user_id", unique=True)
        self.old_tokens_subscription.create_index("user_id", unique=True)
        self.old_tokens_ontime.create_index("user_id", unique=True)
        self.user_points_manager = user_points_manager
        self.plan_features = plan_features
        self.cache_manager = cache_manager

    def fetch_or_cache_subscription(self, user_id: str) -> dict:
        cache_key = f"user_subscription:{user_id}"
        if cached_data := self.cache_manager.get(cache_key):
            return loads(cached_data)
        
        sub_doc = self.subscriptions.find_one({"user_id": user_id})
        if not sub_doc:
            self.apply_or_default_subscription(user_id)
            sub_doc = self.subscriptions.find_one({"user_id": user_id})

        self.cache_manager.set(cache_key, dumps(sub_doc), 3600)  # Cache for 1 hour
        return sub_doc
    
    def purchase_token_exists(self, purchase_token: str) -> bool:
        return bool(
            sub_doc := self.subscriptions.find_one({"purchase_token": purchase_token})
        )

    def get_subscription_by_token(self, purchase_token: str) -> dict:
        return self.subscriptions.find_one({"purchase_token": purchase_token})
    
    def add_subscription_token(self, user_id: str, token: str):
        self.old_tokens_subscription.update_one(
            {"user_id": user_id},
            {"$push": {"tokens": token}},
            upsert=True
        )

    def retrieve_subscription_tokens(self, user_id: str) -> List[str]:
        document = self.old_tokens_subscription.find_one({"user_id": user_id})
        return document["tokens"] if document else []
    

    def retrieve_user_id_by_token(self, token: str) -> Optional[str]:
        document = self.old_tokens_subscription.find_one({"tokens": token})
        return document["user_id"] if document else None
    
    def add_onetime_token(self, user_id: str, token: str, product_purchased: str):
        self.old_tokens_ontime.update_one(
            {"user_id": user_id},
            {"$push": {"purchases": {"token": token, "product": product_purchased}}},
            upsert=True
        )
    def retrieve_onetime_tokens(self, user_id: str) -> List[str]:
        document = self.old_tokens_ontime.find_one({"user_id": user_id})
        if document and "purchases" in document:
            return [purchase["token"] for purchase in document["purchases"]]
        return []

    def find_user_by_token(self, token: str) -> Optional[str]:
        document = self.old_tokens_ontime.find_one({"purchases.token": token})
        return document["user_id"] if document else None
    
    def get_product_by_user_id_and_token(self, user_id: str, token: str) -> Optional[str]:
        document = self.old_tokens_ontime.find_one(
            {"user_id": user_id, "purchases.token": token},
            {"purchases.$": 1}
        )
        if document and "purchases" in document and len(document["purchases"]) > 0:
            return document["purchases"][0]["product"]
        return None

    def get_subscription_type(self, user_id: str) -> SubscriptionType:
        sub_doc = self.fetch_or_cache_subscription(user_id)
        return getattr(SubscriptionType, sub_doc["subscription_type"])
    
    def apply_or_default_subscription(
        self,
        user_id: str,
        purchase_token: str = "",
        subscription_type: SubscriptionType = SubscriptionType.FREE,
        subscription_provider: SubscriptionProvider = SubscriptionProvider.PLAYSTORE,
        update: bool = False
    ) -> None:
        features = self.plan_features[subscription_type]
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": user_id,
            "purchase_token" : purchase_token,
            "subscription_type": subscription_type,
            "subscription_provider": subscription_provider,
            "last_coin_allocation_date": now,
            "last_monthly_reset_date": now,
            "incremental_features": [f.model_dump() for f in features.incremental],
            "static_features": [f.model_dump()  for f in features.static],
            "monthly_limit_features": [f.model_dump() for f in features.monthly_limit],
            "is_cancelled" : False,
            "enabled" : True,
            "monthly_coins": features.monthly_coins.amount,
            "last_daily_reset_date": now,
        }
        
        existing_doc = self.subscriptions.find_one({"user_id": user_id})
        if update or not existing_doc:
            if purchase_token:
                if existing_doc.get("purchase_token") and not existing_doc.get("is_cancelled", False):
                    raise ValueError("Token already used")
                
                if purchase_token in self.retrieve_subscription_tokens(user_id):
                    raise ValueError("Token already used")
                
            self.add_subscription_token(user_id, purchase_token)
            logging.info(f"Applying/Updating subscription for {user_id} token {purchase_token}")
            self.subscriptions.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)
            self.cache_manager.delete(f"user_subscription:{user_id}")
            self.allocate_monthly_coins(user_id, allocate_no_check=True)
            
    

    def enable_disable_subscription(self, user_id: str, enable: bool) -> None:
        self.cache_manager.delete(f"user_subscription:{user_id}")
        self.subscriptions.update_one({"user_id": user_id}, {"$set": {"enabled": enable}}, upsert=True)
            
    def cancel_uncancel_subscription(self, user_id: str, cancel: bool) -> None:
        self.cache_manager.delete(f"user_subscription:{user_id}")
        self.subscriptions.update_one({"user_id": user_id}, {"$set": {"is_cancelled": cancel}}, upsert=True)
      

    def allocate_monthly_coins(self, user_id: str, allocate_no_check: bool = False, multiplier: int = 1) -> None:
        sub_doc = self.fetch_or_cache_subscription(user_id)
        if not sub_doc.get("enabled", True):
            return
        monthly_coins = sub_doc["monthly_coins"]
        logging.info(f"Granting coins {monthly_coins} coins to {user_id}")
        self.user_points_manager.increment_user_points(user_id, monthly_coins * multiplier)
        self.cache_manager.delete(f"user_subscription:{user_id}")


    def reset_monthly_limits(self, user_id: str, reset_no_check: bool = False) -> None:
        sub_doc = self.fetch_or_cache_subscription(user_id)
        if not sub_doc.get("enabled", True):
            return
        
        now = datetime.now(timezone.utc)
        last_reset_date = sub_doc.get("last_monthly_reset_date", datetime.min.replace(tzinfo=timezone.utc))
        # Ensure last_reset_date is timezone-aware
        if last_reset_date.tzinfo is None or last_reset_date.tzinfo.utcoffset(last_reset_date) is None:
            last_reset_date = last_reset_date.replace(tzinfo=timezone.utc)

        if (now - last_reset_date) >= timedelta(days=35) or reset_no_check:
            logging.info(f"Resetting monthly limits for {user_id}")
            default_features = self.plan_features[sub_doc["subscription_type"]].monthly_limit
            for default_feature in default_features:
                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "monthly_limit_features.$[elem].limit": default_feature.limit
                        }
                    },
                    array_filters=[{"elem.name": {"$eq": default_feature.name}}],
                )

            self.subscriptions.update_one(
                {"user_id": user_id}, {"$set": {"last_monthly_reset_date": now}}
            )
            self.cache_manager.delete(f"user_subscription:{user_id}")
            
    def get_feature_value(self, user_id: str, feature_name: str) -> Union[FeatureValueResponse, None]:
        self.reset_all_limits(user_id)
        sub_doc = self.fetch_or_cache_subscription(user_id)
        # Check if the feature is an Incremental feature
        for feature in sub_doc["incremental_features"]:
            if feature_name == feature["name"]:
                return FeatureValueResponse(name=feature_name, main_data=feature["limit"], limit=feature["limit"], fallback_value=None)

        # Check if the feature is a Static feature
        for feature in sub_doc["static_features"]:
            if feature_name == feature["name"]:
                return FeatureValueResponse(name=feature_name, main_data=feature["value"], limit=None, fallback_value=None)

        # Check if the feature is a Monthly Limit feature
        for feature in sub_doc["monthly_limit_features"]:
            if feature_name == feature["name"]:
                if not feature["enabled"]:
                    return FeatureValueResponse(name=feature_name, main_data=feature["fallback_value"], limit=None, fallback_value=feature["fallback_value"])

                main_data = feature["value"] if feature["limit"] > 0 else feature["fallback_value"]
                return FeatureValueResponse(name=feature_name, main_data=main_data, limit=feature["limit"], fallback_value=feature["fallback_value"])
        # Check if the feature is Monthly Coins
        if feature_name == "monthly_coins":
            return FeatureValueResponse(name=feature_name, main_data=sub_doc["monthly_coins"], limit=None, fallback_value=None)

        return None  # Feature not found
    
    def undo_use_feature(self, user_id: str, feature_name: str) -> bool:
        sub_doc = self.fetch_or_cache_subscription(user_id)

        # Incremental features
        for feature in sub_doc.get("incremental_features", []):
            if feature_name == feature["name"]:
                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {"$inc": {"incremental_features.$[elem].limit": 1}},
                    array_filters=[{"elem.name": {"$eq": feature_name}}],
                )
                logging.info(f"Reversed usage for user {user_id}, feature {feature_name}. New limit is {feature['limit'] + 1}")
                self.cache_manager.delete(f"user_subscription:{user_id}")
                return True

        # Monthly limit features
        for feature in sub_doc.get("monthly_limit_features", []):
            if feature_name == feature["name"] and feature["enabled"]:
                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {"$inc": {"monthly_limit_features.$[elem].limit": 1}},
                    array_filters=[{"elem.name": {"$eq": feature_name}}],
                )
                logging.info(f"Reversed monthly limit feature for user {user_id}, feature {feature_name}. New limit is {feature['limit'] + 1}")
                self.cache_manager.delete(f"user_subscription:{user_id}")
                return True

        # If feature does not exist in the document, log and return False
        logging.info(f"No such feature {feature_name} found for user {user_id} to reverse.")
        return False

    def use_feature(self, user_id: str, feature_name: str) -> bool:
        self.reset_all_limits(user_id)
        sub_doc = self.fetch_or_cache_subscription(user_id)
        # Check for Incremental features
        for feature in sub_doc["incremental_features"]:
            if feature_name == feature["name"]:
                if feature["limit"] <= 0:
                    logging.info(f"User {user_id}, plan {sub_doc['subscription_type']} cannot use incremental feature {feature_name}. Usage left {feature['limit']}")
                    return False  # Feature limit reached for incremental features

                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {"$inc": {"incremental_features.$[elem].limit": -1}},
                    array_filters=[{"elem.name": {"$eq": feature_name}}],
                )
                logging.info(f"User {user_id}, plan {sub_doc['subscription_type']} used incremental feature {feature_name}. Usage left {feature['limit']}")
                self.cache_manager.delete(f"user_subscription:{user_id}")
                return True

        # Check for Monthly Limit features
        for feature in sub_doc["monthly_limit_features"]:
            if feature_name == feature["name"]:
                if feature["enabled"]:  # Check if the feature is enabled
                    if feature["limit"] > 0:
                        self.subscriptions.update_one(
                            {"user_id": user_id},
                            {"$inc": {"monthly_limit_features.$[elem].limit": -1}},
                            array_filters=[{"elem.name": {"$eq": feature_name}}]
                        )
                        logging.info(f"User {user_id} used Monthly limit feature {feature_name}. Usage left {feature['limit']}")
                        self.cache_manager.delete(f"user_subscription:{user_id}")
                        return True
                    else:
                        logging.info(f"User {user_id} cannot use Monthly limit feature {feature_name}. Usage left {feature['limit']}")
                        return False
                else:  # If the feature is not enabled
                    logging.info(f"Feature {feature_name} is not enabled. Using fallback value.")
                    return False
        logging.info(f"User {user_id} used feature {feature_name}. Usage left Infinity")
        self.cache_manager.delete(f"user_subscription:{user_id}")
        return True

    def can_use_feature(self, user_id: str, feature_name: str) -> Tuple[bool, Union[str, int]]:
        self.reset_all_limits(user_id)
        sub_doc = self.fetch_or_cache_subscription(user_id)
        # Check for Incremental features
        for feature in sub_doc["incremental_features"]:
            if feature_name == feature["name"]:
                return (feature["limit"] > 0, feature["limit"])

        # Check for Static features
        for feature in sub_doc["static_features"]:
            if feature_name == feature["name"]:
                return (True, feature["value"])

        # Check for Monthly Limit features
        for feature in sub_doc["monthly_limit_features"]:
            if feature_name == feature["name"]:
                main_data = feature["value"] if feature["limit"] > 0 and feature["enabled"] else feature["fallback_value"]
                return (True, main_data)

        return (True, float("inf"))

    def toggle_feature(self, user_id: str, feature_name: str, enabled: bool) -> bool:
        sub_doc = self.fetch_or_cache_subscription(user_id)
        for feature in sub_doc["monthly_limit_features"]:
            if feature_name == feature["name"]:
                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {"$set": {"monthly_limit_features.$[elem].enabled": enabled}},
                    array_filters=[{"elem.name": {"$eq": feature_name}}],
                )
                self.cache_manager.delete(f"user_subscription:{user_id}")  # Invalidate cache
                return True  # Successfully toggled the feature
        return False  # Feature not found
    
    def is_monthly_limit_feature_enabled(self, user_id: str, feature_name: str) -> bool:
        """
        Checks if the given feature is enabled for the user.
        
        :param user_id: The ID of the user.
        :param feature_name: The name of the feature to check.
        :return: True if the feature is enabled, False otherwise.
        """
        sub_doc = self.fetch_or_cache_subscription(user_id)
        return next((feature.get("enabled", False) for feature in sub_doc["monthly_limit_features"] if feature["name"] == feature_name), False)

    
    def get_all_feature_usage_left(self, user_id: str) -> List[Dict[str, Union[str, int]]]:
        self.reset_all_limits(user_id)
        sub_doc = self.fetch_or_cache_subscription(user_id)
        usage_left = [
            {"name": feature["name"], "limit": feature["limit"], "type" : "incremental_features"}
            for feature in sub_doc["incremental_features"]
        ]
        usage_left.extend(
            {"name": feature["name"], "limit": feature["limit"], "type" : "monthly_limit_features"}
            for feature in sub_doc["monthly_limit_features"]
        )
        usage_left.extend(
            {"name": feature["name"], "limit": feature["value"], "type" : "static_features"}
            for feature in sub_doc["static_features"]
        )
        return usage_left

    def reset_incremental_limits(self, user_id: str, reset_no_check: bool = False) -> None:
        sub_doc = self.fetch_or_cache_subscription(user_id)
        if not sub_doc.get("enabled", True):
            return
        now = datetime.now(timezone.utc)
        last_reset_date = sub_doc.get("last_daily_reset_date", datetime.min.replace(tzinfo=timezone.utc))

        if last_reset_date.tzinfo is None or last_reset_date.tzinfo.utcoffset(last_reset_date) is None:
            last_reset_date = last_reset_date.replace(tzinfo=timezone.utc)

        if (now - last_reset_date) >= timedelta(days=1) or reset_no_check:
            logging.info(f"Resetting daily limits for {user_id}")
            default_features = self.plan_features[sub_doc["subscription_type"]].incremental
            for default_feature in default_features:
                self.subscriptions.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "incremental_features.$[elem].limit": default_feature.limit
                        }
                    },
                    array_filters=[{"elem.name": {"$eq": default_feature.name}}],
                )

            self.subscriptions.update_one(
                {"user_id": user_id}, {"$set": {"last_daily_reset_date": now}}
            )
            self.cache_manager.delete(f"user_subscription:{user_id}")


    def reset_all_limits(self, user_id: str, reset_no_check: bool = False) -> None:
        try:
            self.reset_monthly_limits(user_id, reset_no_check)
        except Exception as e:
            logging.error(f"Error reseting monthly limits for {user_id} {e}")
        try:
            self.reset_incremental_limits(user_id, reset_no_check)
        except Exception as e:
            logging.error(f"Error reseting monthly limits for {user_id} {e}")
