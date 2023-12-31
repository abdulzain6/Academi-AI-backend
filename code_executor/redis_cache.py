import contextlib
import redis, logging
from typing import Any, Optional
from bson.json_util import dumps, loads


class RedisCacheManager:
    def __init__(self, redis_client: redis.Redis, ttl: int = 7200) -> None:
        try:
            self.redis_client = redis_client
            self.redis_client.ping()
        except Exception:
            self.redis_client = None
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        try:
            if self.redis_client:
                if value := self.redis_client.get(key):
                    return loads(value)
        except Exception as e:
            logging.error(f"Error in getting cache {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = None, suppress=True) -> None:
        if not ttl:
            ttl = self.ttl
        if suppress:
            try:
                if self.redis_client:
                    self.redis_client.setex(key, ttl, dumps(value))
            except Exception as e:
                print(e)
        else:
            if self.redis_client:
                self.redis_client.setex(key, ttl, dumps(value))
                


    def delete(self, key: str) -> None:
        with contextlib.suppress(redis.RedisError):
            if self.redis_client:
                self.redis_client.delete(key)
