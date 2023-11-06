import logging
import hashlib
from typing import (
    Any,
    Optional
)
from langchain.load.dump import dumps
from langchain.load.load import loads
from langchain.schema import Generation
from langchain.schema.cache import RETURN_VAL_TYPE, BaseCache
from redis import Redis

def _hash(_input: str) -> str:
    """Use a deterministic hashing approach."""
    return hashlib.md5(_input.encode()).hexdigest()


logger = logging.getLogger(__name__)

class RedisCache(BaseCache):
    def __init__(self, redis_: Redis, *, ttl: Optional[int] = None) -> None:
        self.redis = redis_
        self.ttl = ttl

    def _key(self, prompt: str, llm_string: str) -> str:
        return _hash(prompt + llm_string)

    def lookup(self, prompt: str, llm_string: str) -> Optional[RETURN_VAL_TYPE]:
        key = self._key(prompt, llm_string)
        try:
            all_data = self.redis.hgetall(key)
        except Exception as e:
            logger.error(f"Failed to fetch from Redis: {e}")
            return None
                
        if not all_data:
            return None

        generations = []
        for idx, data_str in all_data.items():
            try:
                data = loads(data_str)  # using custom loads
            except Exception as e:
                logger.warning(f"Failed to deserialize data: {e}")
                continue

            if isinstance(data, Generation):
                generations.append(data)
            else:
                logger.warning(f"Unknown data type: {type(data)}")
        
        return generations

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        key = self._key(prompt, llm_string)
        try:
            for idx, gen in enumerate(return_val):
                if not gen.text:
                    continue
                data_str = dumps(gen)  # using custom dumps
                self.redis.hset(key, str(idx), data_str)

            if self.ttl:
                self.redis.expire(key, self.ttl)
        except Exception as e:
            logger.error(f"Failed to update Redis cache: {e}")

    def clear(self, **kwargs: Any) -> None:
        """Clear cache. If `asynchronous` is True, flush asynchronously."""
        asynchronous = kwargs.get("asynchronous", False)
        self.redis.flushdb(asynchronous=asynchronous, **kwargs)

