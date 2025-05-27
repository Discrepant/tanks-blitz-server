# tests/unit/test_redis_client.py
import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from core.redis_client import RedisClient

class TestRedisClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.original_redis_host = os.environ.get('REDIS_HOST')
        self.original_redis_port = os.environ.get('REDIS_PORT')
        RedisClient._instance = None

    def tearDown(self):
        if self.original_redis_host is None:
            os.environ.pop('REDIS_HOST', None)
        else:
            os.environ['REDIS_HOST'] = self.original_redis_host

        if self.original_redis_port is None:
            os.environ.pop('REDIS_PORT', None)
        else:
            os.environ['REDIS_PORT'] = self.original_redis_port
        
        RedisClient._instance = None

    def test_singleton_behavior(self):
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
        with patch('core.redis_client.redis.ConnectionPool'), patch('core.redis_client.redis.Redis'):
            client1 = RedisClient()
            client2 = RedisClient()
            self.assertIs(client1, client2, "RedisClient должен быть singleton.")

    @patch('core.redis_client.redis.Redis')
    @patch('core.redis_client.redis.ConnectionPool')
    async def test_initialization_default_values(self, MockConnectionPool, MockRedis):
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
            
        mock_pool_instance = MockConnectionPool.return_value
        mock_redis_instance = AsyncMock()
        MockRedis.return_value = mock_redis_instance

        client = RedisClient()

        MockConnectionPool.assert_called_once_with(
            host="redis-service", 
            port=6379, 
            decode_responses=True
        )
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        self.assertIs(client.client, mock_redis_instance)

    @patch('core.redis_client.redis.Redis')
    @patch('core.redis_client.redis.ConnectionPool')
    async def test_initialization_with_env_vars(self, MockConnectionPool, MockRedis):
        os.environ['REDIS_HOST'] = "my-custom-redis"
        os.environ['REDIS_PORT'] = "1234"
            
        mock_pool_instance = MockConnectionPool.return_value
        mock_redis_instance = AsyncMock()
        MockRedis.return_value = mock_redis_instance

        client = RedisClient()

        MockConnectionPool.assert_called_once_with(
            host="my-custom-redis", 
            port=1234, 
            decode_responses=True
        )
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        self.assertIs(client.client, mock_redis_instance)

    async def test_get_method(self):
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock() 
        client.client.get.return_value = "test_value"
        
        result = await client.get("test_key")
        
        client.client.get.assert_awaited_once_with("test_key")
        self.assertEqual(result, "test_value")

    async def test_set_method(self):
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.set.return_value = True
        
        result = await client.set("test_key", "test_value", ex=3600)
        
        client.client.set.assert_awaited_once_with("test_key", "test_value", ex=3600)
        self.assertTrue(result)

    async def test_delete_method(self):
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.delete.return_value = 1 
        
        result = await client.delete("test_key1", "test_key2")
        
        client.client.delete.assert_awaited_once_with("test_key1", "test_key2")
        self.assertEqual(result, 1)

    async def test_ping_success(self):
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.ping.return_value = True 
        
        result = await client.ping()
        
        client.client.ping.assert_awaited_once()
        self.assertTrue(result)

    async def test_ping_failure(self):
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.ping.side_effect = Exception("Connection error") 
        
        with patch('builtins.print') as mock_print:
            result = await client.ping()
        
        client.client.ping.assert_awaited_once()
        self.assertFalse(result)
        mock_print.assert_any_call("Redis ping failed: Connection error")

if __name__ == '__main__':
    unittest.main()
