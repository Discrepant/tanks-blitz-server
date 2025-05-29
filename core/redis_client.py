# core/redis_client.py
# Этот модуль предоставляет асинхронный клиент Redis с использованием паттерна Singleton
# и поддержкой мокирования для тестов.
import redis.asyncio as redis # Используем асинхронный клиент Redis
import os
import logging # Добавляем логирование
from unittest.mock import MagicMock, AsyncMock # Для мокирования в тестах

logger = logging.getLogger(__name__) # Инициализация логгера

class RedisClient:
    """
    Асинхронный клиент Redis, реализованный как Singleton.

    Обеспечивает единую точку доступа к соединению с Redis и его мокирование
    для целей тестирования. Инициализация происходит один раз.
    При установленной переменной окружения USE_MOCKS="true" используется мок-клиент.
    """
    _instance = None # Экземпляр Singleton

    def __new__(cls, *args, **kwargs):
        """
        Реализация паттерна Singleton: создает экземпляр только если он еще не существует.
        """
        if not cls._instance:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Инициализирует клиент Redis или его мок.

        Инициализация происходит только один раз. Если переменная окружения
        USE_MOCKS="true", создается мок-клиент Redis с имитацией основных команд
        (ping, get, set, delete) и внутренним хранилищем _mock_storage.
        В противном случае, создается реальный асинхронный клиент Redis
        с использованием пула соединений.
        """
        if not hasattr(self, 'initialized'): # Ensures one-time initialization
            if os.getenv("USE_MOCKS") == "true":
                # Create a mock with the spec of the actual redis.Redis client
                self.client = MagicMock(spec=redis.Redis, name="MockRedisClient") 
                self._mock_storage = {} # Internal storage for the mock

                # Mock core Redis commands with AsyncMock
                self.client.ping = AsyncMock(return_value=True) # ping always successful
            
                async def mock_get(name):
                    # Simulate GET command
                    return self._mock_storage.get(name)
                self.client.get = AsyncMock(side_effect=mock_get)

                async def mock_set(name, value, ex=None):
                    # Simulate SET command, including optional expiration (ex)
                    self._mock_storage[name] = value
                    # Simulate successful SET in Redis (usually returns True or raises an error)
                    # For simplicity, always return True for the mock. Actual client might return None on success for SET.
                    # However, tests might rely on True. If strict redis.Redis spec is needed,
                    # this might need adjustment based on library version or specific test expectations.
                    return True 
                self.client.set = AsyncMock(side_effect=mock_set)

                async def mock_delete(*names):
                    # Simulate DELETE command for one or more keys
                    count = 0
                    for name in names:
                        if name in self._mock_storage:
                            del self._mock_storage[name]
                            count += 1
                    return count # Redis DELETE returns the number of keys deleted
                self.client.delete = AsyncMock(side_effect=mock_delete)
                
                self.initialized = True
                logger.info("Redis client initialized in MOCK mode.")
            else:
                # Configuration for the real Redis client
                self.redis_host = os.getenv("REDIS_HOST", "redis-service") # Redis host, default "redis-service" (for K8s)
                self.redis_port = int(os.getenv("REDIS_PORT", 6379)) # Redis port
                # self.redis_password = os.getenv("REDIS_PASSWORD", None) # Password, if used
                
                # Создание пула соединений для эффективного управления подключениями
                self.pool = redis.ConnectionPool(
                    host=self.redis_host, 
                    port=self.redis_port, 
                    # password=self.redis_password, # Раскомментировать, если используется пароль
                    decode_responses=True # Автоматически декодировать ответы из байтов в строки UTF-8
                )
                # Создание асинхронного клиента Redis с использованием пула соединений
                self.client = redis.Redis(connection_pool=self.pool)
                self.initialized = True
                logger.info(f"Redis client initialized for {self.redis_host}:{self.redis_port}")

    async def get(self, name):
        """
        Асинхронно получает значение ключа из Redis.

        Args:
            name (str): Имя ключа.

        Returns:
            Любое: Значение ключа или None, если ключ не найден.
        """
        return await self.client.get(name)

    async def set(self, name, value, ex=None):
        """
        Асинхронно устанавливает значение ключа в Redis с опциональным временем жизни.

        Args:
            name (str): Имя ключа.
            value (Любое): Значение ключа.
            ex (int, optional): Время жизни ключа в секундах. По умолчанию None.

        Returns:
            bool: True при успехе, иначе может вызвать исключение.
        """
        return await self.client.set(name, value, ex=ex)

    async def delete(self, *names):
        """
        Асинхронно удаляет один или несколько ключей из Redis.

        Args:
            *names (str): Имена ключей для удаления.

        Returns:
            int: Количество удаленных ключей.
        """
        return await self.client.delete(*names)
    
    async def ping(self):
        """
        Асинхронно проверяет соединение с сервером Redis.

        Returns:
            bool: True, если соединение успешно, False в случае ошибки.
        """
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Error pinging Redis: {e}")
            return False

# Пример использования (требует асинхронного контекста для запуска)
# async def example_usage():
#     redis_cli = RedisClient() # Получаем экземпляр Singleton
#     if await redis_cli.ping():
#         logger.info("Successfully connected to Redis.")
#         await redis_cli.set("mykey", "myvalue", ex=60) # Устанавливаем ключ на 60 секунд
#         value = await redis_cli.get("mykey")
#         logger.info(f"Retrieved value from Redis: {value}")
#         await redis_cli.delete("mykey")
#         logger.info(f"Key 'mykey' deleted.")
#     else:
#         logger.error("Failed to connect to Redis.")

if __name__ == '__main__':
    # Для запуска этого примера нужен запущенный цикл событий asyncio.
    # Настройка логирования для примера:
    # logging.basicConfig(level=logging.INFO)
    # import asyncio
    # asyncio.run(example_usage())
    pass # Оставляем pass, так как основной код - это класс и его методы.
