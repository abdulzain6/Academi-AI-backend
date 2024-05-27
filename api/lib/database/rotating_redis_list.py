import redis

class RotatingRedisList:
    def __init__(self, redis_client: redis.Redis, list_key: str, items: list[str]):
        """
        Initializes a Redis connection and sets the initial list.
        
        :param redis_host: The host address for the Redis server.
        :param redis_port: The port number for the Redis server.
        :param list_key: The Redis key under which the list is stored.
        :param items: A list of strings to store in Redis.
        """
        self.redis = redis_client
        self.list_key = list_key
        if redis_client:
            self.redis.delete(list_key)  # Make sure to start fresh for this key
            if items:
                self.redis.rpush(list_key, *items)

    def get_item(self) -> str:
        """
        Retrieves the next item in the list, rotates it to the end, and returns the item.
        
        :return: The next item from the list.
        """
        # Atomically pop the first element and push it back to the end of the list
        item = self.redis.lpop(self.list_key)
        if item is not None:
            self.redis.rpush(self.list_key, item)
            return item.decode('utf-8')  # decode from bytes to str
        else:
            raise IndexError("The list is empty")