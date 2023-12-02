from collections import deque
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import logging
import pymongo
from pymongo.errors import DuplicateKeyError

class UserPoints(BaseModel):
    uid: str
    points: int
    last_claimed: Optional[datetime] = None  # Last time the daily bonus was claimed
    streak_count: int = 0
    
class UserPointsManager:
    def __init__(
        self,
        connection_string: str,
        database_name: str,
        default_points: int = 15,
        daily_points: int = 3,
        weekly_daily_bonus_points: int = 10,
        max_ads_per_day: int = 4,
    ) -> None:
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.points_collection: Collection = self.db["user_points"]
        self.ad_timestamps_collection: Collection = self.db["ad_watch_timestamps"]
        self.default_points = default_points
        self.daily_points = daily_points
        self.max_ads_per_day = max_ads_per_day
        self.weekly_daily_bonus_points = weekly_daily_bonus_points
        self.points_collection.create_index("uid", unique=True)
        self.ad_timestamps_collection.create_index([("uid", pymongo.ASCENDING), ("timestamp", pymongo.ASCENDING)], unique=True)

    def get_ads_watched_today(self, uid: str) -> int:
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count = self.ad_timestamps_collection.count_documents({'uid': uid, 'timestamp': {'$gte': start_of_day}})
        return count

    def can_increment_from_ad(self, uid: str) -> bool:
        if self.get_ads_watched_today(uid) < self.max_ads_per_day:
            self.ad_timestamps_collection.insert_one({'uid': uid, 'timestamp': datetime.now(timezone.utc)})
            return True
        return False

    def get_user_points(self, uid: str) -> UserPoints:
        try:
            if not self.user_exists(uid):
                logging.info(f"Creating points for user, {uid}")
                self.points_collection.insert_one(
                    UserPoints(uid=uid, points=self.default_points).model_dump()
                )

            logging.info(f"Getting points for user, {uid}")
            data = self.points_collection.find_one({"uid": uid}, {"_id": 0})
        except DuplicateKeyError:
            logging.error(f"dup key Error occured for {uid}")
            data = self.points_collection.find_one({"uid" : uid}, {"_id": 0})
            
        return UserPoints(**data)

    def user_exists(self, uid: str) -> bool:
        return self.points_collection.count_documents({"uid": uid}, limit=1) > 0


    def get_streak_day(self, uid: str) -> int:
        user_points: UserPoints = self.get_user_points(uid)
        now = datetime.now(timezone.utc)
        last_claimed: Optional[datetime] = user_points.last_claimed

        if last_claimed and last_claimed.tzinfo is None:
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        # If never claimed, streak is 0
        if not last_claimed:
            return 0

        # Calculate the difference in days
        days_difference = (now - last_claimed).days

        # If the last claim was today, return the streak count
        if days_difference == 0:
            return user_points.streak_count

        # If the last claim was yesterday, the streak continues
        return user_points.streak_count if days_difference == 1 else 0
    
    def is_daily_bonus_claimed(self, uid: str) -> bool:
        """
        Check if the daily bonus has already been claimed by the user identified by uid.

        Returns:
            True if claimed, otherwise False.
        """
        user_points: UserPoints = self.get_user_points(uid)
        now = datetime.now(timezone.utc)
        last_claimed = user_points.last_claimed

        if last_claimed is None:
            return False

        # Ensure last_claimed is also offset-aware
        if (
            last_claimed.tzinfo is None
            or last_claimed.tzinfo.utcoffset(last_claimed) is None
        ):
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        return (now - last_claimed) < timedelta(days=1)

    def claim_daily_bonus(self, uid: str) -> int:
        try:
            logging.info(f"Getting points while claiming bonus for {uid}")
            user_points = self.get_user_points(uid)
        except pymongo.errors.PyMongoError as e:
            logging.error(f"Error getting points while claiming bonus for {uid}")
            raise ValueError("Database operation failed") from e

        now = datetime.now(timezone.utc)
        last_claimed: Optional[datetime] = user_points.last_claimed

        if last_claimed and last_claimed.tzinfo is None:
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        if last_claimed and now - last_claimed < timedelta(days=1):
            return 0

        streak_count: int = (
            user_points.streak_count
            if last_claimed and now - last_claimed < timedelta(days=2)
            else 0
        )
        streak_count += 1
        bonus_points = (
            self.weekly_daily_bonus_points if streak_count == 7 else self.daily_points
        )

        try:
            logging.info(f"Incrementing points while claiming bonus for {uid}")
            self.increment_user_points(uid, bonus_points)
            self.points_collection.update_one(
                {"uid": uid},
                {"$set": {"last_claimed": now, "streak_count": streak_count % 7}},
            )
        except pymongo.errors.PyMongoError as exc:
            logging.error(f"Error incrementing points while claiming bonus for {uid}")
            raise ValueError("Database operation failed") from exc

        return bonus_points

    def increment_user_points(self, uid: str, points: int) -> int:
        if not self.user_exists(uid):
            self.points_collection.insert_one(
                UserPoints(uid=uid, points=self.default_points).model_dump()
            )
        result = self.points_collection.update_one(
            {"uid": uid}, {"$inc": {"points": points}}
        )
        return result.modified_count

    def decrement_user_points(self, uid: str, points: int) -> int:
        if not self.user_exists(uid):
            self.points_collection.insert_one(
                UserPoints(uid=uid, points=self.default_points).model_dump()
            )
        result = self.points_collection.update_one(
            {"uid": uid}, {"$inc": {"points": -points}}
        )
        return result.modified_count

    def time_until_daily_bonus(self, uid: str) -> timedelta:
        user_points: UserPoints = self.get_user_points(uid)
        now = datetime.now(timezone.utc)
        last_claimed: Optional[datetime] = user_points.last_claimed

        if last_claimed is None:
            return timedelta(seconds=0)

        if last_claimed.tzinfo is None:
            last_claimed = last_claimed.replace(tzinfo=timezone.utc)

        time_since_last_claim = now - last_claimed

        if time_since_last_claim >= timedelta(days=1):
            return timedelta(seconds=0)

        return timedelta(days=1) - time_since_last_claim