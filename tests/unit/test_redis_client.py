# tests/unit/test_redis_client.py
# This file contains unit tests for the Redis client (`core.redis_client.RedisClient`).
# Tests verify Singleton behavior, initialization with different configurations,
# and the correctness of the client's main methods (get, set, delete, ping).
import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock # Mocking tools
import redis.asyncio as redis_asyncio 
import redis.exceptions # Import for ConnectionError

# Import the RedisClient class to be tested
from core.redis_client import RedisClient

class TestRedisClient(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для RedisClient.
    Использует `unittest.IsolatedAsyncioTestCase` для асинхронных тестов.
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Сохраняет исходные значения переменных окружения REDIS_HOST и REDIS_PORT,
        чтобы восстановить их после теста. Также сбрасывает экземпляр Singleton RedisClient.
        """
        self.original_redis_host = os.environ.get('REDIS_HOST')
        self.original_redis_port = os.environ.get('REDIS_PORT')
        # Сбрасываем _instance перед каждым тестом для проверки Singleton и корректной инициализации
        RedisClient._instance = None

    def tearDown(self):
        """
        Clean up after each test.
        Restores original REDIS_HOST and REDIS_PORT environment variables.
        Resets the RedisClient Singleton instance.
        """
        # Restore environment variables
        if self.original_redis_host is None:
            os.environ.pop('REDIS_HOST', None)
        else:
            os.environ['REDIS_HOST'] = self.original_redis_host

        if self.original_redis_port is None:
            os.environ.pop('REDIS_PORT', None)
        else:
            os.environ['REDIS_PORT'] = self.original_redis_port
        
        # Reset _instance again in case the test changed it
        RedisClient._instance = None

    def test_singleton_behavior(self):
        """
        Test Singleton behavior for RedisClient.
        Ensures that multiple calls to RedisClient() return the same instance.
        """
        # Remove environment variables to use default values during initialization
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
        # Mock dependencies to avoid real connections
        # Ensure USE_MOCKS is false so it attempts to use redis.ConnectionPool and redis.Redis
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false"
        self.addCleanup(self._restore_use_mocks, original_use_mocks)

        with patch('core.redis_client.redis.ConnectionPool'), patch('core.redis_client.redis.Redis'):
            client1 = RedisClient()
            client2 = RedisClient()
            self.assertIs(client1, client2, "RedisClient should be a Singleton (return the same instance).")

    def _restore_use_mocks(self, original_value):
        """Helper to restore USE_MOCKS environment variable."""
        if original_value is not None:
            os.environ["USE_MOCKS"] = original_value
        elif "USE_MOCKS" in os.environ:
            del os.environ["USE_MOCKS"]

    @patch('core.redis_client.redis.Redis') # Mock for redis.Redis class
    @patch('core.redis_client.redis.ConnectionPool') # Mock for redis.ConnectionPool class
    async def test_initialization_default_values(self, MockConnectionPool, MockRedis):
        """
        Test RedisClient initialization with default values.
        Ensures ConnectionPool and Redis are called with "redis-service" host and port 6379
        when environment variables are not set.
        """
        RedisClient._instance = None # Ensure fresh instance for this test
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false" # Test real client path
        self.addCleanup(self._restore_use_mocks, original_use_mocks)
        
        # Ensure environment variables are not set for this test
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
            
        mock_pool_instance = MockConnectionPool.return_value # Mock ConnectionPool instance
        mock_redis_instance = AsyncMock() # Mock for async Redis client
        MockRedis.return_value = mock_redis_instance # Configure Redis class mock to return our mock instance

        client = RedisClient() # Initialize the client under test

        # Check that ConnectionPool was called with default parameters
        MockConnectionPool.assert_called_once_with(
            host="redis-service", # Expected default host
            port=6379,            # Expected default port
            decode_responses=True # Responses should be decoded
        )
        # Check that Redis was called with the created connection pool
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        # Check that our RedisClient's internal client is the created mock instance
        self.assertIs(client.client, mock_redis_instance)

    @patch('core.redis_client.redis.Redis')
    @patch('core.redis_client.redis.ConnectionPool')
    async def test_initialization_with_env_vars(self, MockConnectionPool, MockRedis):
        """
        Test RedisClient initialization with environment variables.
        Ensures ConnectionPool and Redis are called with host and port
        specified in REDIS_HOST and REDIS_PORT environment variables.
        """
        RedisClient._instance = None # Ensure fresh instance
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false" # Test real client path
        self.addCleanup(self._restore_use_mocks, original_use_mocks)
        
        # Set test values for environment variables
        os.environ['REDIS_HOST'] = "my-custom-redis"
        os.environ['REDIS_PORT'] = "1234"
            
        mock_pool_instance = MockConnectionPool.return_value
        mock_redis_instance = AsyncMock()
        MockRedis.return_value = mock_redis_instance

        client = RedisClient()

        # Check that ConnectionPool was called with values from environment variables
        MockConnectionPool.assert_called_once_with(
            host="my-custom-redis", # Expected host from environment variable
            port=1234,              # Expected port from environment variable
            decode_responses=True
        )
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        self.assertIs(client.client, mock_redis_instance)

    async def test_real_client_ping_connection_error(self):
        """
        Tests that the real Redis client attempts a connection and fails as expected
        if Redis server is not available.
        """
        RedisClient._instance = None # Ensure fresh instance
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false" # Force real client initialization
        self.addCleanup(self._restore_use_mocks, original_use_mocks)

        # Use a non-standard port to increase likelihood of connection failure
        # if a Redis instance is accidentally running on the default port.
        os.environ['REDIS_HOST'] = "localhost"
        os.environ['REDIS_PORT'] = "9999" # Unlikely port for a real Redis

        client = RedisClient()
        
        # Expect a ConnectionError (or a more general RedisError if that's more stable across environments)
        # when trying to ping a non-existent server.
        with self.assertRaises(redis.exceptions.ConnectionError):
            await client.ping()

    # The following tests (get, set, delete, ping_success, ping_failure) 
    # were previously mocking client.client directly.
    # They will be moved to a new class TestRedisClientMockedInstance
    # to test the USE_MOCKS="true" path correctly.

    # Original test_get_method - will be moved and adapted
    # async def test_get_method(self): ...

    # Original test_set_method - will be moved and adapted
    # async def test_set_method(self): ...

    # Original test_delete_method - will be moved and adapted
    # async def test_delete_method(self): ...
    
    # Original test_ping_success - will be moved and adapted
    # async def test_ping_success(self): ...

    # Original test_ping_failure - this specific test for failure of the *mocked* ping
    # might be less relevant if the mock always returns True for ping.
    # The test_ping_success for the mock is more important.
    # The real client connection failure is tested in test_real_client_ping_connection_error.
    # async def test_ping_failure(self): ...


class TestRedisClientMockedInstance(unittest.IsolatedAsyncioTestCase):
    """
    Tests for RedisClient when USE_MOCKS="true", verifying the mocked client behavior.
    """
    def setUp(self):
        """Setup before each test in this class."""
        self.original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "true"
        RedisClient._instance = None # Reset Singleton for each test
        self.redis_client = RedisClient() # This will initialize with the mocked self.client

    def tearDown(self):
        """Clean up after each test in this class."""
        if self.original_use_mocks is not None:
            os.environ["USE_MOCKS"] = self.original_use_mocks
        elif "USE_MOCKS" in os.environ:
            del os.environ["USE_MOCKS"]
        RedisClient._instance = None

    async def test_mock_client_is_magicmock_with_spec(self):
        """Test that the internal client is a MagicMock with the correct spec."""
        self.assertIsInstance(self.redis_client.client, MagicMock)
        # Check if spec was set (MagicMock stores it in _spec_class)
        # redis.Redis is redis.asyncio.client.Redis
        self.assertEqual(self.redis_client.client._spec_class, redis_asyncio.Redis)

    async def test_mock_ping(self):
        """Test the ping method of the mocked client."""
        result = await self.redis_client.ping()
        self.assertTrue(result, "Mocked ping should return True.")
        self.redis_client.client.ping.assert_awaited_once()

    async def test_mock_get(self):
        """Test the get method of the mocked client."""
        # To ensure return_value is used, we disable the side_effect for this test.
        # The side_effect (_mock_get) reads from _mock_storage, which is not what we want to test here.
        self.redis_client.client.get.side_effect = None 
        self.redis_client.client.get.return_value = b"retrieved_value"

        result = await self.redis_client.get("specific_test_key")
        
        self.redis_client.client.get.assert_awaited_once_with("specific_test_key")
        self.assertEqual(result, b"retrieved_value")

    async def test_mock_set(self):
        """Test the set method of the mocked client."""
        result = await self.redis_client.set("another_key", "another_value", ex=60)
        self.assertTrue(result, "Mocked set should return True.")
        self.redis_client.client.set.assert_awaited_once_with("another_key", "another_value", ex=60)
        # Verify it was stored in the mock's internal storage
        self.assertEqual(self.redis_client._mock_storage["another_key"], "another_value")

    async def test_mock_delete(self):
        """Test the delete method of the mocked client."""
        # Pre-populate storage to test deletion
        self.redis_client._mock_storage["delete_me"] = "data"
        self.redis_client._mock_storage["delete_me_too"] = "data2"
        
        result = await self.redis_client.delete("delete_me", "non_existent_key")
        
        self.assertEqual(result, 1, "Mocked delete should return the count of deleted keys.")
        self.redis_client.client.delete.assert_awaited_once_with("delete_me", "non_existent_key")
        self.assertNotIn("delete_me", self.redis_client._mock_storage)
        self.assertIn("delete_me_too", self.redis_client._mock_storage) # Should still be there


if __name__ == '__main__':
    # Run tests if the file is executed directly.
    unittest.main()
