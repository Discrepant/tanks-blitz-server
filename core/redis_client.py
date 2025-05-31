# core/redis_client.py
# This module provides an asynchronous Redis client using the Singleton pattern
# and mock support for tests.
import redis.asyncio as redis # Using asynchronous Redis client
import os
import logging # Added logging
from unittest.mock import MagicMock, AsyncMock # For mocking in tests

logger = logging.getLogger(__name__) # Logger initialization

class RedisClient:
    """
    Asynchronous Redis client, implemented as a Singleton.

    Provides a single point of access to the Redis connection and its mocking
    for testing purposes. Initialization occurs once.
    If USE_MOCKS="true" environment variable is set, a mock client is used.
    """
    _instance = None # Singleton instance

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern implementation: creates an instance only if it doesn't exist yet.
        """
        if not cls._instance:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the Redis client or its mock.

        Initialization occurs only once. If USE_MOCKS="true" environment variable
        is set, a mock Redis client is created with imitation of basic commands
        (ping, get, set, delete) and internal storage _mock_storage.
        Otherwise, a real asynchronous Redis client is created
        using a connection pool.
        """
        if not hasattr(self, 'initialized'): # Ensures one-time initialization
            if os.getenv("USE_MOCKS") == "true":
                self.client = MagicMock(name="MockRedisClientInternal") # Create mock with real client specification
                self._mock_storage = {} # Internal storage for mock

                # Mock basic Redis commands with asynchronous mocks
                self.client.ping = AsyncMock(return_value=True) # ping always successful
            
                async def mock_get(name):
                    # Simulate GET command
                    return self._mock_storage.get(name)
                self.client.get = AsyncMock(side_effect=mock_get)

                async def mock_set(name, value, ex=None):
                    # Simulate SET command, including optional expiration time (ex)
                    self._mock_storage[name] = value
                    return True # Simulate successful SET execution in Redis
                self.client.set = AsyncMock(side_effect=mock_set)

                async def mock_delete(*names):
                    # Simulate DELETE command for one or more keys
                    count = 0
                    for name in names:
                        if name in self._mock_storage:
                            del self._mock_storage[name]
                            count += 1
                    return count # Redis DELETE returns number of deleted keys
                self.client.delete = AsyncMock(side_effect=mock_delete)
                
                self.initialized = True
                logger.info("Redis client initialized in MOCK mode.")
            else:
                # Configuration for real Redis client
                self.redis_host = os.getenv("REDIS_HOST", "redis-service") # Redis host, default "redis-service" (for K8s)
                self.redis_port = int(os.getenv("REDIS_PORT", 6379)) # Redis port
                # self.redis_password = os.getenv("REDIS_PASSWORD", None) # Password, if used
                
                # Create connection pool for efficient connection management
                self.pool = redis.ConnectionPool(
                    host=self.redis_host, 
                    port=self.redis_port, 
                    # password=self.redis_password, # Uncomment if password is used
                    decode_responses=True # Automatically decode responses from bytes to UTF-8 strings
                )
                # Create asynchronous Redis client using connection pool
                self.client = redis.Redis(connection_pool=self.pool)
                self.initialized = True
                logger.info(f"Redis client initialized for {self.redis_host}:{self.redis_port}")

    async def get(self, name):
        """
        Asynchronously gets the value of a key from Redis.

        Args:
            name (str): Key name.

        Returns:
            Any: Key value or None if key is not found.
        """
        return await self.client.get(name)

    async def set(self, name, value, ex=None):
        """
        Asynchronously sets the value of a key in Redis with optional expiration time.

        Args:
            name (str): Key name.
            value (Any): Key value.
            ex (int, optional): Key expiration time in seconds. Default None.

        Returns:
            bool: True on success, otherwise may raise an exception.
        """
        return await self.client.set(name, value, ex=ex)

    async def delete(self, *names):
        """
        Asynchronously deletes one or more keys from Redis.

        Args:
            *names (str): Key names to delete.

        Returns:
            int: Number of deleted keys.
        """
        return await self.client.delete(*names)
    
    async def ping(self):
        """
        Asynchronously checks the connection with the Redis server.

        Returns:
            bool: True if connection is successful, False in case of error.
        """
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Error pinging Redis: {e}")
            return False

# Example usage (requires asynchronous context to run)
# async def example_usage():
#     redis_cli = RedisClient() # Get Singleton instance
#     if await redis_cli.ping():
#         logger.info("Successfully connected to Redis.")
#         await redis_cli.set("mykey", "myvalue", ex=60) # Set key for 60 seconds
#         value = await redis_cli.get("mykey")
#         logger.info(f"Retrieved value from Redis: {value}")
#         await redis_cli.delete("mykey")
#         logger.info(f"Key 'mykey' deleted.")
#     else:
#         logger.error("Failed to connect to Redis.")

if __name__ == '__main__':
    # To run this example, an active asyncio event loop is needed.
    # Logging setup for example:
    # logging.basicConfig(level=logging.INFO)
    # import asyncio
    # asyncio.run(example_usage())
    pass # Keep pass, as the main code is the class and its methods.
