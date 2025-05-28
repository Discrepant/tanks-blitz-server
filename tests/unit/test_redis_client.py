# tests/unit/test_redis_client.py
# Этот файл содержит модульные тесты для клиента Redis (`core.redis_client.RedisClient`).
# Тесты проверяют поведение Singleton, инициализацию с различными конфигурациями
# и корректность работы основных методов клиента (get, set, delete, ping).
import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock # Инструменты для мокирования

# Импортируем тестируемый класс RedisClient
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
        Очистка после каждого теста.
        Восстанавливает исходные значения переменных окружения REDIS_HOST и REDIS_PORT.
        Сбрасывает экземпляр Singleton RedisClient.
        """
        # Восстанавливаем переменные окружения
        if self.original_redis_host is None:
            os.environ.pop('REDIS_HOST', None)
        else:
            os.environ['REDIS_HOST'] = self.original_redis_host

        if self.original_redis_port is None:
            os.environ.pop('REDIS_PORT', None)
        else:
            os.environ['REDIS_PORT'] = self.original_redis_port
        
        # Снова сбрасываем _instance на случай, если тест его изменил
        RedisClient._instance = None

    def test_singleton_behavior(self):
        """
        Тест поведения Singleton для RedisClient.
        Проверяет, что повторные вызовы конструктора RedisClient возвращают один и тот же экземпляр.
        """
        # Удаляем переменные окружения, чтобы использовать значения по умолчанию при инициализации
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
        # Мокируем зависимости, чтобы избежать реальных соединений
        with patch('core.redis_client.redis.ConnectionPool'), patch('core.redis_client.redis.Redis'):
            client1 = RedisClient()
            client2 = RedisClient()
            self.assertIs(client1, client2, "RedisClient должен быть реализован как Singleton (возвращать тот же экземпляр).")

    @patch('core.redis_client.redis.Redis') # Мок для класса redis.Redis
    @patch('core.redis_client.redis.ConnectionPool') # Мок для класса redis.ConnectionPool
    async def test_initialization_default_values(self, MockConnectionPool, MockRedis):
        """
        Тест инициализации RedisClient со значениями по умолчанию.
        Проверяет, что ConnectionPool и Redis вызываются с хостом "redis-service" и портом 6379,
        когда переменные окружения не установлены.
        """
        RedisClient._instance = None
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false"

        def cleanup_use_mocks():
            if original_use_mocks is not None:
                os.environ["USE_MOCKS"] = original_use_mocks
            elif "USE_MOCKS" in os.environ:
                del os.environ["USE_MOCKS"]
        self.addCleanup(cleanup_use_mocks)
        
        # Убеждаемся, что переменные окружения не установлены для этого теста
        os.environ.pop('REDIS_HOST', None)
        os.environ.pop('REDIS_PORT', None)
            
        mock_pool_instance = MockConnectionPool.return_value # Мок экземпляра ConnectionPool
        mock_redis_instance = AsyncMock() # Мок для асинхронного клиента Redis
        MockRedis.return_value = mock_redis_instance # Настраиваем мок класса Redis, чтобы он возвращал наш мок-экземпляр

        client = RedisClient() # Инициализируем тестируемый клиент

        # Проверяем, что ConnectionPool был вызван с параметрами по умолчанию
        MockConnectionPool.assert_called_once_with(
            host="redis-service", # Ожидаемый хост по умолчанию
            port=6379,            # Ожидаемый порт по умолчанию
            decode_responses=True # Ответы должны декодироваться
        )
        # Проверяем, что Redis был вызван с созданным пулом соединений
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        # Проверяем, что внутренний клиент нашего RedisClient - это созданный мок-экземпляр
        self.assertIs(client.client, mock_redis_instance)

    @patch('core.redis_client.redis.Redis')
    @patch('core.redis_client.redis.ConnectionPool')
    async def test_initialization_with_env_vars(self, MockConnectionPool, MockRedis):
        """
        Тест инициализации RedisClient с использованием переменных окружения.
        Проверяет, что ConnectionPool и Redis вызываются с хостом и портом,
        указанными в переменных окружения REDIS_HOST и REDIS_PORT.
        """
        RedisClient._instance = None
        original_use_mocks = os.environ.get("USE_MOCKS")
        os.environ["USE_MOCKS"] = "false"

        def cleanup_use_mocks():
            if original_use_mocks is not None:
                os.environ["USE_MOCKS"] = original_use_mocks
            elif "USE_MOCKS" in os.environ:
                del os.environ["USE_MOCKS"]
        self.addCleanup(cleanup_use_mocks)
        
        # Устанавливаем тестовые значения для переменных окружения
        os.environ['REDIS_HOST'] = "my-custom-redis"
        os.environ['REDIS_PORT'] = "1234"
            
        mock_pool_instance = MockConnectionPool.return_value
        mock_redis_instance = AsyncMock()
        MockRedis.return_value = mock_redis_instance

        client = RedisClient()

        # Проверяем, что ConnectionPool был вызван со значениями из переменных окружения
        MockConnectionPool.assert_called_once_with(
            host="my-custom-redis", # Ожидаемый хост из переменной окружения
            port=1234,              # Ожидаемый порт из переменной окружения
            decode_responses=True
        )
        MockRedis.assert_called_once_with(connection_pool=mock_pool_instance)
        self.assertIs(client.client, mock_redis_instance)

    async def test_get_method(self):
        """
        Тест метода `get` клиента Redis.
        Проверяет, что внутренний метод `client.get` вызывается с правильным ключом
        и что результат возвращается корректно.
        """
        # Мокируем ConnectionPool, чтобы RedisClient мог инициализироваться без реального соединения
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock() # Мокируем сам клиент Redis (экземпляр redis.Redis)
        client.client.get.return_value = "test_value" # Настраиваем возвращаемое значение для get
        
        result = await client.get("test_key") # Вызываем тестируемый метод
        
        client.client.get.assert_awaited_once_with("test_key") # Проверяем, что мок был вызван с "test_key"
        self.assertEqual(result, "test_value", "Метод get должен вернуть значение от внутреннего клиента.")

    async def test_set_method(self):
        """
        Тест метода `set` клиента Redis.
        Проверяет, что внутренний метод `client.set` вызывается с правильными аргументами
        (ключ, значение, время жизни) и что результат возвращается корректно.
        """
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.set.return_value = True # Имитируем успешную установку
        
        result = await client.set("test_key", "test_value", ex=3600) # `ex` - время жизни в секундах
        
        client.client.set.assert_awaited_once_with("test_key", "test_value", ex=3600)
        self.assertTrue(result, "Метод set должен вернуть True при успехе.")

    async def test_delete_method(self):
        """
        Тест метода `delete` клиента Redis.
        Проверяет, что внутренний метод `client.delete` вызывается с правильными ключами
        и что результат (количество удаленных ключей) возвращается корректно.
        """
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.delete.return_value = 1 # Имитируем удаление одного ключа
        
        result = await client.delete("test_key1", "test_key2") # Пытаемся удалить два ключа
        
        client.client.delete.assert_awaited_once_with("test_key1", "test_key2")
        self.assertEqual(result, 1, "Метод delete должен вернуть количество удаленных ключей.")

    async def test_ping_success(self):
        """
        Тест успешного выполнения команды `ping`.
        Проверяет, что внутренний метод `client.ping` вызывается и возвращает True.
        """
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.ping.return_value = True # Имитируем успешный ping
        
        result = await client.ping()
        
        client.client.ping.assert_awaited_once() # Проверяем, что ping был вызван
        self.assertTrue(result, "Метод ping должен вернуть True при успехе.")

    async def test_ping_failure(self):
        """
        Тест неудачного выполнения команды `ping`.
        Проверяет, что внутренний метод `client.ping` вызывается, обрабатывает исключение
        и возвращает False. Также проверяет, что ошибка логируется (через print в текущей реализации).
        """
        with patch('core.redis_client.redis.ConnectionPool'):
            client = RedisClient()
        client.client = AsyncMock()
        client.client.ping.side_effect = Exception("Connection error") # Имитируем ошибку соединения
        
        # Мокируем встроенную функцию print, чтобы проверить ее вызов
        # В реальном приложении здесь бы использовался логгер.
        with patch('core.redis_client.logger.error') as mock_logger_error: # Заменяем на мок логгера
            result = await client.ping()
        
        client.client.ping.assert_awaited_once()
        self.assertFalse(result, "Метод ping должен вернуть False при ошибке.")
        # Проверяем, что print (теперь logger.error) был вызван с сообщением об ошибке
        mock_logger_error.assert_any_call("Ошибка при проверке соединения с Redis (ping): Connection error")


if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()
