# tests/test_integration.py
# Этот файл содержит интеграционные тесты для проверки взаимодействия
# между сервером аутентификации и игровым сервером.
# Тесты запускают оба сервера как отдельные процессы и отправляют им запросы.

import asyncio
import unittest
import subprocess # Для запуска серверных процессов
import time # Для задержек, чтобы серверы успели запуститься
import json # Для работы с JSON-сообщениями
import logging # Для логирования

# Добавляем путь к корневой директории проекта для корректного импорта модулей.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Предполагаемые порты из конфигураций серверов (main.py файлов)
AUTH_PORT = 8888 # Порт сервера аутентификации
GAME_PORT = 8889 # TCP-порт игрового сервера
HOST = '127.0.0.1' # Используем localhost для всех тестов

# Настройка логирования для тестов
# Можно настроить уровень и формат по необходимости
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# Закомментированный блок ниже предназначался для динамического добавления тестовых пользователей
# в MOCK_USERS_DB сервера аутентификации. Однако, при запуске серверов как отдельных процессов,
# прямое изменение MOCK_USERS_DB из тестового процесса не повлияет на запущенный сервер.
# Тестовые пользователи должны быть предопределены в `auth_server/user_service.py`
# или сервер должен предоставлять API для их добавления/удаления (что не является частью текущей задачи).
# Для текущих тестов используются пользователи "integ_user" и "integ_user_fail",
# которые должны быть в MOCK_USERS_DB.
# try:
#     from auth_server.user_service import MOCK_USERS_DB
#     # Убедимся, что тестовые пользователи существуют
#     if "integ_user" not in MOCK_USERS_DB:
#         MOCK_USERS_DB["integ_user"] = "integ_pass"
#     if "integ_user_fail" not in MOCK_USERS_DB:
#         MOCK_USERS_DB["integ_user_fail"] = "correct_pass" # Пароль для теста на неверный пароль
#     if "integ_user2" not in MOCK_USERS_DB: # Для теста чата
#         MOCK_USERS_DB["integ_user2"] = "integ_pass2"
# except ImportError:
#     logger.warning("Не удалось импортировать MOCK_USERS_DB для инициализации тестовых пользователей в test_integration.")
    # Можно добавить заглушку, если это критично для тестов без запущенного сервера,
    # но тесты все равно не пройдут, если сервер не знает этих пользователей.
    # MOCK_USERS_DB = {"integ_user": "integ_pass", "integ_user_fail": "correct_pass", "integ_user2": "integ_pass2"}


async def tcp_client_request(host: str, port: int, message: str, timeout: float = 2.0) -> str:
    """
    Асинхронная функция для отправки TCP-запроса на указанный хост и порт.

    Args:
        host (str): Хост сервера.
        port (int): Порт сервера.
        message (str): Сообщение для отправки (ожидается строка, будет закодирована в UTF-8).
                       Предполагается, что сообщение уже содержит символ новой строки, если он нужен серверу.
        timeout (float, optional): Таймаут для операций соединения и чтения. По умолчанию 2.0 секунды.

    Returns:
        str: Ответ сервера в виде строки, или сообщение об ошибке/таймауте.
    """
    try:
        # Устанавливаем соединение с таймаутом
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        # Отправляем сообщение, добавляя перевод строки, если его нет (хотя лучше, чтобы он был в message)
        # Серверы в проекте ожидают \n как разделитель.
        full_message = message if message.endswith('\n') else message + '\n'
        writer.write(full_message.encode('utf-8')) 
        await writer.drain() # Ожидаем отправки данных

        # Читаем ответ до символа новой строки с таймаутом
        response_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=timeout)
        response_str = response_bytes.decode('utf-8').strip() # Декодируем и очищаем ответ

        writer.close() # Закрываем соединение
        await writer.wait_closed() # Ожидаем полного закрытия
        logger.debug(f"Запрос к {host}:{port} ('{message.strip()}'): Ответ '{response_str}'")
        return response_str
    except asyncio.TimeoutError:
        logger.warning(f"ТАЙМАУТ: Нет ответа от {host}:{port} для '{message.strip()}' в течение {timeout}с")
        return f"TIMEOUT: No response from {host}:{port} for '{message.strip()}' within {timeout}s"
    except ConnectionRefusedError:
        logger.error(f"ОТКАЗ В СОЕДИНЕНИИ: Не удалось подключиться к {host}:{port}")
        return f"CONN_REFUSED: Could not connect to {host}:{port}"
    except Exception as e:
        logger.exception(f"ОШИБКА TCP-клиента при запросе к {host}:{port} ('{message.strip()}'): {e}")
        return f"ERROR: {e}"


class TestServerIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Класс для интеграционных тестов серверов.
    Запускает сервер аутентификации и игровой сервер как отдельные процессы
    перед выполнением тестов и останавливает их после.
    """
    auth_server_process: subprocess.Popen | None = None # Процесс сервера аутентификации
    game_server_process: subprocess.Popen | None = None # Процесс игрового сервера

    @classmethod
    def setUpClass(cls):
        """
        Метод класса, вызываемый один раз перед запуском всех тестов в классе.
        Запускает сервер аутентификации и игровой сервер.
        Устанавливает переменные окружения, включая USE_MOCKS="true",
        чтобы серверы использовали мок-объекты для внешних зависимостей (Kafka, Redis).
        """
        logger.info("Инициализация тестового окружения для интеграционных тестов...")
        # Запускаем серверы в отдельных процессах.
        # Используем переменную окружения PYTHONPATH, чтобы серверы могли найти свои модули.
        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        # Устанавливаем USE_MOCKS в "true" для использования моков Kafka/Redis/RabbitMQ на серверах
        env["USE_MOCKS"] = "true" 
        # env["REDIS_HOST"] = "localhost" # Закомментировано, так как используется мок
        # env["REDIS_PORT"] = "6379"      # Закомментировано
        # env["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:29092" # Закомментировано
        # env["RABBITMQ_HOST"] = "localhost" # Закомментировано
        
        # Адреса и порты, на которых серверы должны слушать
        # Эти переменные используются самими серверами при запуске
        env["AUTH_SERVER_HOST"] = HOST # Сервер аутентификации слушает на localhost
        env["AUTH_SERVER_PORT"] = str(AUTH_PORT) # Порт сервера аутентификации
        env["GAME_SERVER_TCP_HOST"] = HOST # Игровой TCP-сервер слушает на localhost
        env["GAME_SERVER_TCP_PORT"] = str(GAME_PORT) # Порт игрового TCP-сервера
        env["GAME_SERVER_UDP_PORT"] = "9999"  # Порт игрового UDP-сервера (если он используется в тестах)
        
        logger.info(f"Переменные окружения для запуска серверов: {env.get('PYTHONPATH')}, USE_MOCKS={env.get('USE_MOCKS')}")

        # Запуск сервера аутентификации
        logger.info(f"Запуск сервера аутентификации (auth_server.main) на {HOST}:{AUTH_PORT}...")
        cls.auth_server_process = subprocess.Popen(
            [sys.executable, "-m", "auth_server.main"], # Запускаем как модуль
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Запуск игрового сервера
        logger.info(f"Запуск игрового сервера (game_server.main) TCP на {HOST}:{GAME_PORT}...")
        cls.game_server_process = subprocess.Popen(
            [sys.executable, "-m", "game_server.main"], # Запускаем как модуль
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        
        # Даем серверам время на запуск. Это важно, особенно на медленных машинах или в CI.
        logger.info("Ожидание запуска серверов (2 секунды)...")
        time.sleep(2) # Увеличено время ожидания для надежности

        # Проверяем, что серверы действительно запустились (хотя бы что процессы не упали сразу)
        if cls.auth_server_process.poll() is not None:
            auth_stdout = cls.auth_server_process.stdout.read().decode(errors='ignore') if cls.auth_server_process.stdout else ""
            auth_stderr = cls.auth_server_process.stderr.read().decode(errors='ignore') if cls.auth_server_process.stderr else ""
            logger.error(f"Сервер аутентификации не запустился. STDOUT: {auth_stdout} STDERR: {auth_stderr}")
            raise RuntimeError("Сервер аутентификации не запустился.")
        
        if cls.game_server_process.poll() is not None:
            game_stdout = cls.game_server_process.stdout.read().decode(errors='ignore') if cls.game_server_process.stdout else ""
            game_stderr = cls.game_server_process.stderr.read().decode(errors='ignore') if cls.game_server_process.stderr else ""
            logger.error(f"Игровой сервер не запустился. STDOUT: {game_stdout} STDERR: {game_stderr}")
            raise RuntimeError("Игровой сервер не запустился.")
        
        logger.info("Серверы успешно запущены для интеграционных тестов.")


    @classmethod
    def tearDownClass(cls):
        """
        Метод класса, вызываемый один раз после выполнения всех тестов в классе.
        Останавливает серверные процессы.
        """
        logger.info("Остановка серверных процессов после интеграционных тестов...")
        if cls.auth_server_process:
            logger.info("Остановка сервера аутентификации...")
            cls.auth_server_process.terminate() # Завершаем процесс
            cls.auth_server_process.wait(timeout=5) # Ожидаем завершения с таймаутом
            # Выводим STDOUT и STDERR для отладки, если что-то пошло не так
            auth_stdout = cls.auth_server_process.stdout.read().decode(errors='ignore') if cls.auth_server_process.stdout else ""
            auth_stderr = cls.auth_server_process.stderr.read().decode(errors='ignore') if cls.auth_server_process.stderr else ""
            logger.debug(f"\n--- STDOUT Сервера Аутентификации ---\n{auth_stdout}")
            logger.debug(f"--- STDERR Сервера Аутентификации ---\n{auth_stderr}")
            logger.info("Сервер аутентификации остановлен.")
        
        if cls.game_server_process:
            logger.info("Остановка игрового сервера...")
            cls.game_server_process.terminate()
            cls.game_server_process.wait(timeout=5)
            game_stdout = cls.game_server_process.stdout.read().decode(errors='ignore') if cls.game_server_process.stdout else ""
            game_stderr = cls.game_server_process.stderr.read().decode(errors='ignore') if cls.game_server_process.stderr else ""
            logger.debug(f"\n--- STDOUT Игрового Сервера ---\n{game_stdout}")
            logger.debug(f"--- STDERR Игрового Сервера ---\n{game_stderr}")
            logger.info("Игровой сервер остановлен.")
        
        logger.info("Все серверы остановлены.")

    async def asyncSetUp(self):
        """
        Асинхронная настройка перед каждым тестом.
        Проверяет, что серверные процессы все еще работают.
        """
        if self.auth_server_process and self.auth_server_process.poll() is not None:
            self.fail("Сервер аутентификации неожиданно завершился перед тестом.")
        if self.game_server_process and self.game_server_process.poll() is not None:
            self.fail("Игровой сервер неожиданно завершился перед тестом.")

    # --- Тесты для Сервера Аутентификации ---
    async def test_01_auth_server_login_success(self):
        """Тест успешного логина напрямую на сервере аутентификации (JSON)."""
        # Используем пользователя, который должен быть в MOCK_USERS_DB сервера аутентификации.
        # Предполагается, что "integ_user":"integ_pass" существует.
        request_payload = {"action": "login", "username": "integ_user", "password": "integ_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "success", f"Ответ сервера: {response_str}")
            self.assertIn("integ_user успешно аутентифицирован", response_json.get("message", ""), "Сообщение об успехе неверно.")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON из ответа сервера аутентификации: {response_str}")

    async def test_02_auth_server_login_failure_wrong_pass(self):
        """Тест неудачного логина (неверный пароль) напрямую на сервере аутентификации (JSON)."""
        request_payload = {"action": "login", "username": "integ_user_fail", "password": "wrong_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("Неверный пароль", response_json.get("message", ""), "Сообщение о неверном пароле неверно.")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_03_auth_server_login_failure_user_not_found(self):
        """Тест неудачного логина (пользователь не найден) напрямую на сервере аутентификации (JSON)."""
        request_payload = {"action": "login", "username": "non_existent_user_integ", "password": "some_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("Пользователь не найден", response_json.get("message", ""), "Сообщение 'Пользователь не найден' неверно.")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_04_auth_server_invalid_json_action(self): # Переименован для ясности
        """Тест неверного действия (action) в JSON-запросе на сервере аутентификации."""
        request_payload = {"action": "UNKNOWN_ACTION_JSON_TEST", "data": "some_payload"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "error", f"Ответ сервера: {response_str}")
            self.assertEqual(response_json.get("message"), "Неизвестное или отсутствующее действие", f"Сообщение об ошибке неверно: {response_str}")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")
            
    # --- Тесты для Игрового Сервера (взаимодействие с Сервером Аутентификации) ---
    async def test_05_game_server_login_success_via_auth_client(self): # Переименовано для ясности
        """Тест успешного логина на игровом сервере, который использует AuthClient (текстовый протокол)."""
        # Игровой сервер (TCP-хендлер) ожидает текстовый формат "LOGIN username password".
        # AuthClient внутри игрового сервера затем отправляет JSON на сервер аутентификации.
        # Предполагается, что пользователь "integ_user":"integ_pass" существует на сервере аутентификации.
        response = await tcp_client_request(HOST, GAME_PORT, "LOGIN integ_user integ_pass") # Текстовый запрос к игровому серверу
        self.assertTrue(response.startswith("LOGIN_SUCCESS"), f"Ответ от игрового сервера: {response}")
        # Токен сессии теперь должен возвращаться из AuthClient и включаться в ответ tcp_handler игрового сервера.
        # Пример: "LOGIN_SUCCESS Пользователь integ_user успешно аутентифицирован. Token: integ_user" (если токен - это имя пользователя)
        # Проверяем, что сообщение содержит "Token:", если ожидается токен.
        # В текущей реализации auth_server возвращает сообщение об успехе как токен, что подхватывается game_server's AuthClient.
        self.assertIn("Token:", response, "Ответ должен содержать информацию о токене.")

    async def test_06_game_server_login_failure_via_auth_client(self): # Переименовано
        """Тест неудачного логина на игровом сервере (неверные данные для AuthClient)."""
        response = await tcp_client_request(HOST, GAME_PORT, "LOGIN integ_user wrong_pass_for_game")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        # Сообщение об ошибке приходит от сервера аутентификации через AuthClient.
        self.assertIn("Неверный пароль", response, "Сообщение должно указывать на неверный пароль от сервера аутентификации.")

    async def test_07_game_server_login_user_not_found_via_auth_client(self): # Переименовано
        """Тест неудачного логина на игровом сервере (пользователь не найден в AuthClient)."""
        response = await tcp_client_request(HOST, GAME_PORT, "LOGIN nosuchuser_integ gamepass")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        self.assertIn("Пользователь не найден", response, "Сообщение должно указывать, что пользователь не найден (от сервера аутентификации).")

    async def test_08_game_server_chat_after_login(self):
        """
        Тест взаимодействия двух клиентов в чате игрового сервера после логина.
        Проверяет отправку и получение сообщений.
        """
        # Клиент 1 подключается и логинится
        reader1, writer1 = await asyncio.open_connection(HOST, GAME_PORT)
        login_cmd1 = "LOGIN integ_user integ_pass\n"
        writer1.write(login_cmd1.encode('utf-8'))
        await writer1.drain()
        login_response1_bytes = await reader1.readuntil(b"\n")
        login_response1 = login_response1_bytes.decode('utf-8')
        self.assertTrue(login_response1.startswith("LOGIN_SUCCESS"), f"Клиент 1: Неудачный логин: {login_response1.strip()}")
        
        # Пропускаем приветственные сообщения сервера для клиента 1
        await reader1.readuntil(b"\n") # "SERVER: Добро пожаловать..."
        # Сообщение о присоединении самого себя (если сервер так настроен) или ожидание
        # Это сообщение может быть "SERVER: Игрок integ_user присоединился..."
        # Для стабильности теста, лучше не полагаться на точное количество этих сообщений,
        # а читать до тех пор, пока не получим ожидаемое сообщение чата или таймаут.

        # Клиент 2 подключается и логинится
        # Убедимся, что пользователь "integ_user2" существует в MOCK_USERS_DB на сервере аутентификации
        # (предполагается, что он добавлен для тестов).
        reader2, writer2 = await asyncio.open_connection(HOST, GAME_PORT)
        login_cmd2 = "LOGIN integ_user2 integ_pass2\n" # Используем другого пользователя
        writer2.write(login_cmd2.encode('utf-8'))
        await writer2.drain()
        login_response2_bytes = await reader2.readuntil(b"\n")
        login_response2 = login_response2_bytes.decode('utf-8')
        self.assertTrue(login_response2.startswith("LOGIN_SUCCESS"), f"Клиент 2: Неудачный логин: {login_response2.strip()}")

        # Пропускаем приветственные сообщения и сообщения о присоединении для клиента 2
        await reader2.readuntil(b"\n") # "SERVER: Добро пожаловать..."
        # Клиент 2 получит сообщение о том, что Клиент 1 уже в комнате
        join_msg_c1_for_c2 = await reader2.readuntil(b"\n") 
        self.assertIn(f"SERVER: Игрок {login_cmd1.split()[1]} присоединился".encode('utf-8'), join_msg_c1_for_c2, "Клиент 2 не получил сообщение о присоединении Клиента 1")
        # Клиент 1 получит сообщение о том, что Клиент 2 присоединился
        join_msg_c2_for_c1 = await reader1.readuntil(b"\n")
        self.assertIn(f"SERVER: Игрок {login_cmd2.split()[1]} присоединился".encode('utf-8'), join_msg_c2_for_c1, "Клиент 1 не получил сообщение о присоединении Клиента 2")


        # Клиент 1 отправляет сообщение в чат
        say_cmd1 = "SAY Hello from client1\n"
        writer1.write(say_cmd1.encode('utf-8'))
        await writer1.drain()

        # Клиент 1 (отправитель) должен получить свое сообщение (эхо от broadcast)
        echo_msg_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd1.split()[1]}: Hello from client1".encode('utf-8'), echo_msg_for_c1, "Клиент 1 не получил эхо своего сообщения.")

        # Клиент 2 должен получить сообщение от Клиента 1
        chat_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd1.split()[1]}: Hello from client1".encode('utf-8'), chat_msg_for_c2, "Клиент 2 не получил сообщение от Клиента 1.")


        # Клиент 2 отправляет сообщение в чат
        say_cmd2 = "SAY Hi from client2\n"
        writer2.write(say_cmd2.encode('utf-8'))
        await writer2.drain()

        # Клиент 2 (отправитель) должен получить свое сообщение
        echo_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd2.split()[1]}: Hi from client2".encode('utf-8'), echo_msg_for_c2, "Клиент 2 не получил эхо своего сообщения.")
        
        # Клиент 1 должен получить сообщение от Клиента 2
        chat_msg_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd2.split()[1]}: Hi from client2".encode('utf-8'), chat_msg_for_c1, "Клиент 1 не получил сообщение от Клиента 2.")


        # Корректное закрытие соединений
        writer1.write(b"QUIT\n")
        await writer1.drain()
        # Ожидаем ответ на QUIT и закрытие соединения сервером
        await reader1.readuntil(b"\n") # Ответ "SERVER: Вы выходите..."
        self.assertTrue(await reader1.read(100) == b'', "Соединение Клиента 1 не было закрыто сервером после QUIT.")
        writer1.close()
        await writer1.wait_closed()

        writer2.write(b"QUIT\n")
        await writer2.drain()
        await reader2.readuntil(b"\n") # Ответ "SERVER: Вы выходите..."
        self.assertTrue(await reader2.read(100) == b'', "Соединение Клиента 2 не было закрыто сервером после QUIT.")
        writer2.close()
        await writer2.wait_closed()

    async def test_09_game_server_quit_command(self):
        """Тест корректной обработки команды QUIT на игровом сервере."""
        reader, writer = await asyncio.open_connection(HOST, GAME_PORT)

        # Логин
        login_cmd = "LOGIN integ_user integ_pass\n"
        writer.write(login_cmd.encode('utf-8'))
        await writer.drain()
        await reader.readuntil(b"\n") # Ответ LOGIN_SUCCESS
        await reader.readuntil(b"\n") # "SERVER: Добро пожаловать..."
        # Сообщение о присоединении (если это первый игрок, то только о себе)
        # Для надежности теста, лучше не зависеть от точного количества этих сообщений,
        # если тест не проверяет именно их.
        try: # Пытаемся прочитать еще одно сообщение (может быть о присоединении)
            await asyncio.wait_for(reader.readuntil(b"\n"), timeout=0.5)
        except asyncio.TimeoutError:
            pass # Ничего страшного, если дополнительного сообщения не было

        # Отправляем команду QUIT
        writer.write(b"QUIT\n")
        await writer.drain()

        # Сервер должен отправить подтверждение QUIT и затем закрыть соединение.
        try:
            response_quit_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=1.0)
            self.assertIn("SERVER: Вы выходите из комнаты...".encode('utf-8'), response_quit_bytes, "Не получено подтверждение выхода.")

            # После подтверждения QUIT, сервер должен закрыть соединение.
            # Попытка чтения из закрытого сокета должна вернуть EOF (пустые байты) или вызвать ошибку.
            eof_signal = await asyncio.wait_for(reader.read(100), timeout=1.0) # Читаем оставшиеся данные
            self.assertEqual(eof_signal, b"", "Соединение не было закрыто сервером после QUIT (ожидался EOF).")

        except asyncio.TimeoutError:
            self.fail("Сервер не ответил на команду QUIT или не закрыл соединение в течение таймаута.")
        except asyncio.IncompleteReadError:
            # Это ожидаемое поведение, если сервер закрыл соединение сразу после отправки подтверждения QUIT.
            logger.info("IncompleteReadError после QUIT, что ожидаемо, если сервер закрыл соединение.")
            pass
        finally:
            # Гарантируем закрытие writer'а со стороны клиента.
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()


if __name__ == '__main__':
    # Запуск тестов.
    # setUpClass и tearDownClass позаботятся о запуске и остановке серверов.
    unittest.main()
