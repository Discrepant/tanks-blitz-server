import asyncio
import grpc
from concurrent import futures
import logging

# Предполагается, что .proto файлы находятся в ./protos, а сгенерированные файлы - в ./grpc_generated относительно пути выполнения этого скрипта
# При необходимости скорректируйте sys.path или структурируйте как правильный пакет
# import sys # Больше не требуется для этого
# import os # Больше не требуется для этого
# Добавьте родительский каталог 'auth_server' в sys.path, чтобы разрешить импорт из соседних каталогов, если 'protos' находится вне 'auth_server'
# Например, если 'protos' и 'auth_server' являются соседними каталогами в корневом каталоге.
# Это также помогает найти 'grpc_generated', если это подпакет 'auth_server'.
# sys.path.append(os.path.join(os.path.dirname(__file__), 'grpc_generated')) # Удалено
# sys.path.append(os.path.dirname(os.path.abspath(__file__))) # Добавьте сам auth_server для user_service # Удалено

# Используйте полные импорты, предполагая, что 'auth_server' - это пакет верхнего уровня, видимый в PYTHONPATH
from auth_server.grpc_generated import auth_service_pb2
from auth_server.grpc_generated import auth_service_pb2_grpc
from auth_server.user_service import UserService
from passlib.hash import pbkdf2_sha256 # Импорт перемещен на верхний уровень

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AuthServiceServicer(auth_service_pb2_grpc.AuthServiceServicer):
    def __init__(self, user_svc_instance):
        self.user_service = user_svc_instance
        logging.info("AuthServiceServicer initialized.")

    async def AuthenticateUser(self, request, context):
        logging.info(f"AuthenticateUser called for username: {request.username}")
        authenticated, message = await self.user_service.authenticate_user(request.username, request.password)
        token = ""
        if authenticated:
            token = request.username # Пока используем имя пользователя в качестве токена
            logging.info(f"User {request.username} authenticated successfully. Token: {token}")
        else:
            logging.warning(f"Authentication failed for user {request.username}: {message}")

        return auth_service_pb2.AuthResponse(
            authenticated=authenticated,
            message=message,
            token=token
        )

    async def RegisterUser(self, request, context):
        logging.info(f"RegisterUser called for username: {request.username}")
        # Пока регистрация не полностью реализована с user_service,
        # поэтому мы возвращаем имитацию успеха или "не реализовано".
        # Попробуем использовать user_service.create_user, если это соответствует требуемому потоку.
        # user_service.create_user является асинхронным и принимает (username, password_hash)
        # Здесь нам нужно было бы хешировать пароль. Для простоты, представим, что это не реализовано.

        # Если бы вы хотели это реализовать:
        # from passlib.hash import pbkdf2_sha256 # Удалено отсюда, перемещено наверх
        password_hash = pbkdf2_sha256.hash(request.password) # pbkdf2_sha256 теперь из глобальных переменных модуля
        success, message = await self.user_service.create_user(request.username, password_hash)
        if success:
            logging.info(f"User {request.username} registered successfully.")
            return auth_service_pb2.AuthResponse(authenticated=False, message="Регистрация прошла успешно. Пожалуйста, войдите в систему.", token="")
        else:
            logging.warning(f"Registration failed for user {request.username}: {message}")
            return auth_service_pb2.AuthResponse(authenticated=False, message=f"Ошибка регистрации: {message}", token="")

        # message = "Регистрация на этом сервере пока не реализована."
        # logging.info(message)
        # return auth_service_pb2.AuthResponse(
        #     authenticated=False,
        #     message=message,
        #     token=""
        # )

async def serve():
    # Инициализация клиента Redis (и, возможно, других сервисов, от которых зависит user_service)
    # Предполагается, что user_service имеет асинхронный метод initialize или может быть инициализирован заранее.
    # В этом примере предположим, что UserService может быть создан напрямую,
    # и его зависимость от Redis обрабатывается в его методах или при его создании.

    # Проверьте, является ли initialize_redis_client асинхронным или синхронным в user_service.py
    # Он синхронный.
    UserService.initialize_redis_client() # Вызов метода класса для настройки Redis

    user_svc_instance = UserService() # Создание экземпляра UserService

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_service_pb2_grpc.add_AuthServiceServicer_to_server(
        AuthServiceServicer(user_svc_instance), server
    )

    port = "50051"
    server.add_insecure_port(f'[::]:{port}')
    logging.info(f"gRPC Auth Server starting on port {port}...")
    await server.start()
    logging.info(f"gRPC Auth Server started successfully on port {port}.")
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logging.info("gRPC Auth Server stopping...")
        await server.stop(0)
        logging.info("gRPC Auth Server stopped.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
