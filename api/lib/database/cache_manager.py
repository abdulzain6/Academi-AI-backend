import contextlib
import redis, logging
from typing import Any, Optional, Protocol
from bson.json_util import dumps, loads

class CacheProtocol(Protocol):
    def get(self, key: str) -> Optional[Any]:
        ...

    def set(self, key: str, value: Any) -> None:
        ...

    def delete(self, key: str) -> None:
        ...

class RedisCacheManager:
    def __init__(self, redis_client: redis.Redis, ttl: int = 7200) -> None:
        try:
            self.redis_client = redis_client
            self.redis_client.ping()
        except redis.ConnectionError:
            self.redis_client = None
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        try:
            if self.redis_client:
                if value := self.redis_client.get(key):
                    logging.info(f"Using cached value of {key}")
                    return loads(value)
        except Exception as e:
            logging.error(f"Error in getting cache {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        with contextlib.suppress(Exception):
            if self.redis_client:
                logging.info(f"Setting cached value for {key}")
                self.redis_client.setex(key, self.ttl, dumps(value))
                logging.info(f"Set successfully cached value for {key}")

    def delete(self, key: str) -> None:
        with contextlib.suppress(redis.RedisError):
            if self.redis_client:
                self.redis_client.delete(key)