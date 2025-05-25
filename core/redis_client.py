# core/redis_client.py
import redis.asyncio as redis # Используем асинхронный клиент
import os

class RedisClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.redis_host = os.getenv("REDIS_HOST", "redis-service") # Имя сервиса K8s
            self.redis_port = int(os.getenv("REDIS_PORT", 6379))
            # self.redis_password = os.getenv("REDIS_PASSWORD", None) # Если используется пароль
            
            # Пул соединений
            self.pool = redis.ConnectionPool(
                host=self.redis_host, 
                port=self.redis_port, 
                # password=self.redis_password, 
                decode_responses=True # Декодировать ответы из байтов в строки
            )
            self.client = redis.Redis(connection_pool=self.pool)
            self.initialized = True
            print(f"Redis client initialized for {self.redis_host}:{self.redis_port}")

    async def get(self, name):
        return await self.client.get(name)

    async def set(self, name, value, ex=None): # ex - время жизни в секундах
        return await self.client.set(name, value, ex=ex)

    async def delete(self, *names):
        return await self.client.delete(*names)
    
    async def ping(self):
        try:
            return await self.client.ping()
        except Exception as e:
            print(f"Redis ping failed: {e}")
            return False

# Пример использования (для асинхронного кода)
# async def example_usage():
#     redis_cli = RedisClient()
#     if await redis_cli.ping():
#         await redis_cli.set("mykey", "myvalue", ex=60)
#         value = await redis_cli.get("mykey")
#         print(f"Got value from Redis: {value}")
#     else:
#         print("Could not connect to Redis.")

if __name__ == '__main__':
    # Для запуска этого примера нужен запущенный event loop
    # import asyncio
    # asyncio.run(example_usage())
    pass
