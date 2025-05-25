# tests/load/locustfile_auth.py
from locust import User, task, between
import socket
import time
import random

# Простой TCP клиент для Locust
# Locust обычно используется для HTTP, но можно адаптировать для других протоколов.
# Этот клиент очень упрощенный. Для более сложных сценариев TCP
# может потребоваться кастомный TcpUser или использование библиотеки,
# которая интегрируется с gevent (используемым Locust).

class TCPClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._socket = None

    def connect(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
        except Exception as e:
            if self._socket:
                self._socket.close()
            self._socket = None
            raise e

    def send(self, data):
        if not self._socket:
            self.connect()
        self._socket.sendall(data.encode())

    def recv(self, length=1024):
        if not self._socket:
            # Попытка получить данные без активного соединения не имеет смысла
            return None 
        return self._socket.recv(length).decode()

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None

class AuthUser(User):
    wait_time = between(1, 3) # Время ожидания пользователя между задачами
    host = "localhost" # Хост сервера аутентификации
    port = 8888        # Порт сервера аутентификации

    # Возможные пользователи для теста (из auth_server.user_service.MOCK_USERS_DB)
    test_credentials = [
        ("player1", "password123"),
        ("testuser", "testpass"),
        ("nonexistent", "fakepass") # Для проверки неудачных попыток
    ]

    def on_start(self):
        """ Вызывается при старте "пользователя" Locust """
        self.client = TCPClient(self.host, self.port)
        try:
            self.client.connect()
            print(f"User connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect on_start: {e}")
            # Если не удалось подключиться, можно остановить пользователя или пометить как неудачу
            self.environment.events.request.fire(
                request_type="TCP_CONNECT", name="on_start_connect", response_time=0, response_length=0, exception=e, context=self.environment
            )


    @task
    def login_task(self):
        if not self.client._socket: # Если сокет не активен, пытаемся переподключиться
            try:
                self.client.connect()
            except Exception as e:
                self.environment.events.request.fire(
                    request_type="TCP_CONNECT", name="login_task_reconnect", response_time=0, response_length=0, exception=e, context=self.environment
                )
                return # Не можем продолжить без соединения

        username, password = random.choice(self.test_credentials)
        request_data = f"LOGIN {username} {password}"
        
        start_time = time.time()
        try:
            self.client.send(request_data)
            response = self.client.recv(1024)
            end_time = time.time()
            
            if response and ("AUTH_SUCCESS" in response or "AUTH_FAILURE" in response):
                self.environment.events.request.fire(
                    request_type="TCP_AUTH",
                    name=f"login_{username}",
                    response_time=(end_time - start_time) * 1000,
                    response_length=len(response),
                    context=self.environment,
                    exception=None
                )
            else:
                raise Exception(f"Unexpected or no response: {response}")

        except Exception as e:
            end_time = time.time()
            self.environment.events.request.fire(
                request_type="TCP_AUTH",
                name=f"login_{username}_error",
                response_time=(end_time - start_time) * 1000,
                response_length=0,
                exception=e,
                context=self.environment
            )
            # В случае ошибки можно закрыть и переоткрыть соединение при следующей задаче
            self.client.close()


    def on_stop(self):
        """ Вызывается при остановке "пользователя" Locust """
        if self.client:
            self.client.close()
        print("User stopped and disconnected.")

# Для запуска Locust: locust -f tests/load/locustfile_auth.py --host=your-auth-server-host
# Если сервер на localhost, --host можно опустить, если он указан в AuthUser.host
# locust -f tests/load/locustfile_auth.py AuthUser --headless -u 10 -r 2 --run-time 30s
# Запустит 10 пользователей с интенсивностью 2 пользователя в секунду на 30 секунд без UI.
