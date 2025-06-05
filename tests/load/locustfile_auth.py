# tests/load/locustfile_auth.py
# Этот файл содержит сценарий нагрузочного тестирования для сервера аутентификации
# с использованием Locust. Он имитирует пользователей, которые подключаются к серверу
# и пытаются выполнить вход.

from locust import User, task, between # Импортируем классы User, task и between из Locust
import socket # Для TCP-соединений
import time # Для измерения времени отклика
import random # Для выбора случайных учетных данных
import logging # Добавляем логирование
import json # Added to fix NameError

# Настройка логирования для locustfile
# Уровень INFO будет достаточен, чтобы не перегружать вывод при большом количестве пользователей.
logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)


# Простой TCP-клиент для Locust.
# Locust обычно используется для HTTP-тестирования, но его можно адаптировать
# для других протоколов, создав собственного клиента.
# Этот клиент очень упрощен. Для более сложных TCP-сценариев
# может потребоваться создание кастомного TcpUser или использование библиотеки,
# которая интегрируется с gevent (используемым Locust для асинхронности).

class TCPClient:
    """
    Простой TCP-клиент для отправки и получения данных.
    Используется в AuthUser для взаимодействия с TCP-сервером аутентификации.
    """
    def __init__(self, host: str, port: int):
        """
        Инициализирует TCP-клиент.

        Args:
            host (str): Хост сервера.
            port (int): Порт сервера.
        """
        self.host = host
        self.port = port
        self._socket: socket.socket | None = None # Сокет для соединения

    def connect(self):
        """
        Устанавливает TCP-соединение с сервером.
        В случае ошибки закрывает сокет и выбрасывает исключение.
        """
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
            logger.debug(f"TCPClient: Успешное подключение к {self.host}:{self.port}")
        except Exception as e:
            if self._socket:
                self._socket.close()
            self._socket = None # Сбрасываем сокет в случае ошибки
            logger.error(f"TCPClient: Ошибка подключения к {self.host}:{self.port} - {e}")
            raise # Повторно выбрасываем исключение, чтобы Locust мог его обработать

    def send(self, data: str):
        """
        Отправляет данные на сервер.
        Если соединение не установлено, сначала пытается подключиться.

        Args:
            data (str): Строка данных для отправки (будет закодирована в UTF-8).
        """
        if not self._socket: # Если сокет не существует или был закрыт
            logger.debug("TCPClient: Сокет неактивен, попытка переподключения перед отправкой.")
            self.connect() # Пытаемся установить новое соединение
        
        try:
            self._socket.sendall(data.encode('utf-8')) # Отправляем данные в кодировке UTF-8
            logger.debug(f"TCPClient: Отправлено: {data.strip()}")
        except Exception as e:
            logger.error(f"TCPClient: Ошибка при отправке данных - {e}")
            self.close() # Закрываем сокет при ошибке отправки
            raise

    def recv(self, length: int = 1024) -> str | None:
        """
        Получает данные от сервера.

        Args:
            length (int, optional): Максимальное количество байт для получения.
                                    По умолчанию 1024.

        Returns:
            str | None: Декодированная строка ответа или None, если сокет неактивен.
        """
        if not self._socket:
            # Попытка получить данные без активного соединения не имеет смысла.
            logger.warning("TCPClient: Попытка получения данных при неактивном сокете.")
            return None 
        try:
            response_bytes = self._socket.recv(length)
            response_str = response_bytes.decode('utf-8').strip()
            logger.debug(f"TCPClient: Получено: {response_str}")
            return response_str
        except Exception as e:
            logger.error(f"TCPClient: Ошибка при получении данных - {e}")
            self.close() # Закрываем сокет при ошибке получения
            raise

    def close(self):
        """Закрывает сокет, если он открыт."""
        if self._socket:
            try:
                self._socket.close()
                logger.debug("TCPClient: Сокет закрыт.")
            except Exception as e:
                logger.error(f"TCPClient: Ошибка при закрытии сокета - {e}")
            finally:
                self._socket = None

class AuthUser(User):
    """
    Класс пользователя Locust для тестирования сервера аутентификации.
    Имитирует поведение пользователя, который входит в систему.
    """
    wait_time = between(1, 3) # Время ожидания пользователя Locust между выполнением задач (в секундах)
    host = "localhost" # Хост сервера аутентификации (можно переопределить из командной строки Locust)
    port = 8889        # Порт сервера аутентификации (ИЗМЕНЕНО НА 8889)

    # Список учетных данных для тестирования. Взят из MOCK_USERS_DB в auth_server.user_service.
    test_credentials = [
        ("player1", "password123"),   # Существующий пользователь, верный пароль
        ("testuser", "testpass"),     # Существующий пользователь, верный пароль
        ("testuser", "wrongpass"),    # Существующий пользователь, неверный пароль
        ("nonexistent", "fakepass")   # Несуществующий пользователь
    ]

    def on_start(self):
        """
        Вызывается один раз при старте виртуального пользователя ( locust "user").
        Инициализирует TCP-клиент и устанавливает соединение.
        """
        self.client = TCPClient(self.host, self.port)
        try:
            self.client.connect()
            # Используем logger вместо print для консистентности и контроля вывода
            logger.info(f"Пользователь Locust подключился к {self.host}:{self.port}") 
        except Exception as e:
            logger.error(f"Не удалось подключиться в on_start: {e}")
            # Если не удалось подключиться, можно остановить пользователя или зарегистрировать ошибку в Locust.
            # Это позволяет Locust отслеживать сбои подключения как часть статистики.
            self.environment.events.request.fire(
                request_type="TCP_CONNECT",      # Тип запроса (можно задать свой)
                name="on_start_connect_failure", # Имя для группировки в статистике Locust
                response_time=0,                 # Время отклика (0, так как не было ответа)
                response_length=0,               # Длина ответа (0)
                exception=e,                     # Передаем исключение
                context=self.environment         # Контекст окружения Locust
            )


    @task # Декоратор @task указывает, что это задача, которую будет выполнять пользователь Locust
    def login_task(self):
        """
        Задача пользователя: попытка входа в систему.
        Выбирает случайные учетные данные и отправляет LOGIN-запрос.
        Регистрирует успех или неудачу в статистике Locust.
        """
        if not self.client._socket: # Если сокет не активен (например, после ошибки), пытаемся переподключиться
            try:
                logger.info("Сокет неактивен, попытка переподключения в login_task...")
                self.client.connect()
            except Exception as e:
                # Регистрируем ошибку переподключения
                self.environment.events.request.fire(
                    request_type="TCP_CONNECT", name="login_task_reconnect_failure", 
                    response_time=0, response_length=0, exception=e, context=self.environment
                )
                return # Не можем продолжить без соединения

        # Выбираем случайную пару (имя пользователя, пароль) из списка
        username, password = random.choice(self.test_credentials)
        # Формируем LOGIN-запрос (старый формат, для совместимости с текущим auth_server)
        # ВАЖНО: Сервер аутентификации был обновлен для приема JSON. Этот запрос должен быть JSON.
        # request_data = f"LOGIN {username} {password}\n" 
        request_data_dict = {"action": "login", "username": username, "password": password}
        request_data_json = json.dumps(request_data_dict) + "\n" # Добавляем \n для readuntil()
        
        start_time = time.time() # Засекаем время начала запроса
        try:
            self.client.send(request_data_json) # Отправляем данные
            response = self.client.recv(1024)   # Получаем ответ (до 1024 байт)
            end_time = time.time()              # Засекаем время окончания
            
            # Проверяем, содержит ли ответ ожидаемые маркеры успеха или неудачи
            # Новый формат ответа сервера аутентификации - JSON.
            # Пример: {"status": "success", "message": "...", "session_id": "..."}
            #         {"status": "failure", "message": "..."}
            if response:
                try:
                    response_json = json.loads(response)
                    status = response_json.get("status")
                    if status == "success" or status == "failure":
                        self.environment.events.request.fire(
                            request_type="TCP_AUTH",               # Тип запроса
                            name=f"login_{username}_{status}",       # Имя для статистики (например, "login_player1_success")
                            response_time=int((end_time - start_time) * 1000), # Время отклика в миллисекундах
                            response_length=len(response.encode('utf-8')), # Длина ответа в байтах
                            context=self.environment,              # Контекст
                            exception=None                         # Нет исключения = успех с точки зрения Locust
                        )
                    else:
                        raise Exception(f"Неожиданный статус в JSON-ответе: {status}. Ответ: {response}")
                except json.JSONDecodeError:
                     raise Exception(f"Не удалось декодировать JSON из ответа: {response}")
            else: # Если ответ пустой или None
                raise Exception(f"Пустой или отсутствующий ответ от сервера для {username}")

        except Exception as e: # Если произошла ошибка (например, соединение разорвано, таймаут)
            end_time = time.time()
            # Регистрируем ошибку в Locust
            self.environment.events.request.fire(
                request_type="TCP_AUTH",
                name=f"login_{username}_error", # Имя для ошибок этого типа запроса
                response_time=int((end_time - start_time) * 1000),
                response_length=0, # Длина ответа 0 при ошибке (или фактическая, если удалось что-то прочитать)
                exception=e,       # Передаем исключение
                context=self.environment
            )
            # В случае ошибки можно закрыть соединение, чтобы следующая задача начала с чистого листа.
            # Либо можно попытаться продолжить с тем же соединением, если ошибка не связана с ним.
            self.client.close()


    def on_stop(self):
        """
        Вызывается один раз при остановке виртуального пользователя Locust.
        Закрывает TCP-соединение.
        """
        if self.client:
            self.client.close()
        logger.info("Пользователь Locust остановлен и отсоединен.")

# Инструкции по запуску Locust (если запускать из командной строки):
# 1. Убедитесь, что сервер аутентификации запущен.
# 2. Перейдите в директорию, где находится этот locustfile.
# 3. Команда для запуска с веб-интерфейсом:
#    locust -f tests/load/locustfile_auth.py
#    Затем откройте http://localhost:8089 в браузере.
#    В поле "Host" укажите, например, http://localhost:8888 (хотя для TCP это не совсем так используется,
#    но Locust ожидает хост; важно, что AuthUser.host и AuthUser.port корректны).
#
# 4. Команда для запуска без веб-интерфейса (headless):
#    locust -f tests/load/locustfile_auth.py AuthUser --headless -u 10 -r 2 --run-time 30s
#    Описание параметров:
#    -u 10: количество одновременных пользователей
#    -r 2: количество пользователей, запускаемых в секунду (spawn rate)
#    --run-time 30s: продолжительность теста (30 секунд)
#
# Примечание: Так как сервер аутентификации теперь ожидает JSON,
# login_task был обновлен для отправки JSON-запросов.
# Старый формат "LOGIN username password" больше не должен работать.
