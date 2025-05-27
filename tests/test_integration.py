import asyncio
import unittest
import subprocess # Для запуска серверов
import time
import json # Added import

# Добавляем путь к корневой директории проекта
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Предполагаемые порты из файлов main.py
AUTH_PORT = 8888
GAME_PORT = 8889
HOST = '127.0.0.1' # Используем localhost для тестов

# Убедимся, что тестовые пользователи существуют в auth_server.user_service.MOCK_USERS_DB
# Это важно, если MOCK_USERS_DB инициализируется при импорте user_service
# try:
#     from auth_server.user_service import MOCK_USERS_DB
#     if "integ_user" not in MOCK_USERS_DB:
#         MOCK_USERS_DB["integ_user"] = "integ_pass"
#     if "integ_user_fail" not in MOCK_USERS_DB:
#         MOCK_USERS_DB["integ_user_fail"] = "correct_pass"
# except ImportError:
#     print("Не удалось импортировать MOCK_USERS_DB для инициализации тестовых пользователей.")
    # Можно добавить заглушку, если это критично для тестов без запущенного сервера
    # MOCK_USERS_DB = {"integ_user": "integ_pass", "integ_user_fail": "correct_pass"}


async def tcp_client_request(host, port, message, timeout=2.0):
    """Отправляет TCP запрос и возвращает ответ."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        writer.write(message.encode() + b"\n") # Добавляем \n
        await writer.drain()

        response_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=timeout)
        response = response_bytes.decode().strip()

        writer.close()
        await writer.wait_closed()
        return response
    except asyncio.TimeoutError:
        return f"TIMEOUT: No response from {host}:{port} for '{message.strip()}' within {timeout}s"
    except ConnectionRefusedError:
        return f"CONN_REFUSED: Could not connect to {host}:{port}"
    except Exception as e:
        return f"ERROR: {e}"


class TestServerIntegration(unittest.IsolatedAsyncioTestCase):
    auth_server_process = None
    game_server_process = None

    @classmethod
    def setUpClass(cls):
        # Запускаем серверы в отдельных процессах
        # Используем PYTHONPATH, чтобы серверы нашли свои модули
        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        env["USE_MOCKS"] = "true"
        # env["REDIS_HOST"] = "localhost" # Commented out for mock mode
        # env["REDIS_PORT"] = "6379"      # Commented out for mock mode
        # env["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:29092" # Commented out for mock mode
        # env["RABBITMQ_HOST"] = "localhost" # Commented out for mock mode
        
        # Server addresses and ports for the servers themselves to listen on
        env["AUTH_SERVER_HOST"] = "localhost" # For GameServer's AuthClient
        env["AUTH_SERVER_PORT"] = "8888"      # For GameServer's AuthClient and for Auth Server to bind
        env["GAME_SERVER_TCP_PORT"] = "8889"  # For GameServer's TCP server to bind
        env["GAME_SERVER_UDP_PORT"] = "9999"  # For GameServer's UDP server to bind

        # Запуск сервера аутентификации
        cls.auth_server_process = subprocess.Popen(
            [sys.executable, "-m", "auth_server.main"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Запуск игрового сервера
        cls.game_server_process = subprocess.Popen(
            [sys.executable, "-m", "game_server.main"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Даем серверам время на запуск
        time.sleep(2) # Увеличено время ожидания

        # Проверяем, что серверы запустились (хотя бы что процессы существуют)
        if cls.auth_server_process.poll() is not None:
            print("Auth server stdout:", cls.auth_server_process.stdout.read().decode(errors='ignore'))
            print("Auth server stderr:", cls.auth_server_process.stderr.read().decode(errors='ignore'))
            raise RuntimeError("Сервер аутентификации не запустился.")
        if cls.game_server_process.poll() is not None:
            print("Game server stdout:", cls.game_server_process.stdout.read().decode(errors='ignore'))
            print("Game server stderr:", cls.game_server_process.stderr.read().decode(errors='ignore'))
            raise RuntimeError("Игровой сервер не запустился.")
        print("Серверы запущены для интеграционных тестов.")


    @classmethod
    def tearDownClass(cls):
        # Останавливаем серверы
        if cls.auth_server_process:
            cls.auth_server_process.terminate()
            cls.auth_server_process.wait(timeout=5)
            print("\n--- Auth Server STDOUT ---")
            print(cls.auth_server_process.stdout.read().decode(errors='ignore'))
            print("--- Auth Server STDERR ---")
            print(cls.auth_server_process.stderr.read().decode(errors='ignore'))
        if cls.game_server_process:
            cls.game_server_process.terminate()
            cls.game_server_process.wait(timeout=5)
            print("\n--- Game Server STDOUT ---")
            print(cls.game_server_process.stdout.read().decode(errors='ignore'))
            print("--- Game Server STDERR ---")
            print(cls.game_server_process.stderr.read().decode(errors='ignore'))
        print("Серверы остановлены.")

    async def asyncSetUp(self):
        # Убедимся, что серверы все еще работают перед каждым тестом
        if self.auth_server_process.poll() is not None:
            self.fail("Сервер аутентификации упал перед тестом.")
        if self.game_server_process.poll() is not None:
            self.fail("Игровой сервер упал перед тестом.")

    async def test_01_auth_server_login_success(self):
        """Тест успешного логина на сервере аутентификации."""
        # Используем пользователя, который должен быть в MOCK_USERS_DB
        # auth_server.user_service.MOCK_USERS_DB["integ_user"] = "integ_pass" (сделано в setUpClass)
        request_msg = json.dumps({"action": "login", "username": "integ_user", "password": "integ_pass"})
        response_str = await tcp_client_request(HOST, AUTH_PORT, request_msg)
        response_json = json.loads(response_str)
        self.assertEqual(response_json.get("status"), "success", f"Ответ: {response_str}")
        self.assertIn("integ_user успешно аутентифицирован", response_json.get("message", ""))

    async def test_02_auth_server_login_failure_wrong_pass(self):
        """Тест неудачного логина (неверный пароль) на сервере аутентификации."""
        request_msg = json.dumps({"action": "login", "username": "integ_user_fail", "password": "wrong_pass"})
        response_str = await tcp_client_request(HOST, AUTH_PORT, request_msg)
        response_json = json.loads(response_str)
        self.assertEqual(response_json.get("status"), "failure", f"Ответ: {response_str}")
        self.assertIn("Неверный пароль", response_json.get("message", ""))

    async def test_03_auth_server_login_failure_user_not_found(self):
        """Тест неудачного логина (пользователь не найден) на сервере аутентификации."""
        request_msg = json.dumps({"action": "login", "username": "non_existent_user_integ", "password": "some_pass"})
        response_str = await tcp_client_request(HOST, AUTH_PORT, request_msg)
        response_json = json.loads(response_str)
        self.assertEqual(response_json.get("status"), "failure", f"Ответ: {response_str}")
        self.assertIn("Пользователь не найден", response_json.get("message", ""))

    async def test_04_auth_server_invalid_command(self):
        """Тест неверной команды на сервере аутентификации."""
        request_msg = json.dumps({"action": "UNKNOWN_ACTION_JSON_TEST", "data": "some_payload"})
        response_str = await tcp_client_request(HOST, AUTH_PORT, request_msg)
        response_json = json.loads(response_str)
        self.assertEqual(response_json.get("status"), "error", f"Ответ: {response_str}")
        self.assertEqual(response_json.get("message"), "Unknown or missing action", f"Ответ: {response_str}")

    async def test_05_game_server_login_success_via_auth(self):
        """Тест успешного логина на игровом сервере (через сервер аутентификации)."""
        # Предполагается, что integ_user:integ_pass существует на сервере аутентификации
        response = await tcp_client_request(GAME_PORT, GAME_PORT, "LOGIN integ_user integ_pass")
        self.assertTrue(response.startswith("LOGIN_SUCCESS"), f"Ответ от игрового сервера: {response}")
        # Токен сейчас не возвращается auth_server'ом, поэтому не проверяем его наличие.
        # Если бы возвращался, было бы: self.assertIn("Token:", response)

    async def test_06_game_server_login_failure_via_auth(self):
        """Тест неудачного логина на игровом сервере (неверные данные для auth)."""
        response = await tcp_client_request(GAME_PORT, GAME_PORT, "LOGIN integ_user wrong_pass_for_game")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        self.assertIn("Неверный пароль", response) # Это сообщение от auth_server

    async def test_07_game_server_login_user_not_found_via_auth(self):
        """Тест неудачного логина на игровом сервере (пользователь не найден в auth)."""
        response = await tcp_client_request(GAME_PORT, GAME_PORT, "LOGIN nosuchuser_integ gamepass")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        self.assertIn("Пользователь не найден", response) # Это сообщение от auth_server

    async def test_08_game_server_chat_after_login(self):
        """Два клиента подключаются, логинятся и общаются в чате."""
        # Клиент 1
        reader1, writer1 = await asyncio.open_connection(HOST, GAME_PORT)
        # Логин клиента 1
        writer1.write(b"LOGIN integ_user integ_pass\n")
        await writer1.drain()
        login_response1 = await reader1.readuntil(b"\n")
        self.assertTrue(login_response1.decode().startswith("LOGIN_SUCCESS"), f"Login1: {login_response1.decode()}")
        # Приветственное сообщение от сервера (может быть несколько)
        # Пропускаем их, чтобы добраться до сообщений чата
        # Например, "SERVER: Добро пожаловать..." и "SERVER: Игрок ... присоединился..."
        await reader1.readuntil(b"\n") # "Добро пожаловать"
        # Второе сообщение о присоединении может быть, а может и нет, если это первый игрок
        # Для надежности, лучше не ждать его жестко, если тест не на это.
        # Вместо этого, мы будем ждать конкретных сообщений чата.

        # Клиент 2
        reader2, writer2 = await asyncio.open_connection(HOST, GAME_PORT)
        # Логин клиента 2 (используем другого пользователя, если MOCK_USERS_DB это позволяет,
        # или того же, если сервер это корректно обрабатывает - сейчас для простоты того же)
        # Для этого теста создадим еще одного пользователя в MOCK_USERS_DB
        # if "integ_user2" not in MOCK_USERS_DB: MOCK_USERS_DB["integ_user2"] = "integ_pass2" # Commented out
        # Перезапускать сервер аутентификации не нужно, т.к. MOCK_USERS_DB - глобальный объект модуля
        # и изменения в нем подхватятся при следующем вызове authenticate_user

        # Логин клиента 2
        writer2.write(b"LOGIN integ_user2 integ_pass2\n")
        await writer2.drain()
        login_response2 = await reader2.readuntil(b"\n")
        self.assertTrue(login_response2.decode().startswith("LOGIN_SUCCESS"), f"Login2: {login_response2.decode()}")
        # Пропускаем приветственные сообщения для клиента 2
        await reader2.readuntil(b"\n") # "Добро пожаловать"
        await reader2.readuntil(b"\n") # "integ_user присоединился" (от первого клиента)
        # Может быть еще одно "integ_user2 присоединился", если сервер шлет его всем


        # Клиент 1 отправляет сообщение
        writer1.write(b"SAY Hello from client1\n")
        await writer1.drain()

        # Клиент 2 должен получить сообщение от клиента 1
        # Сообщение о присоединении второго игрока могло прийти первому клиенту
        # Прочитаем его, если оно есть
        try:
            # Ожидаем "SERVER: Игрок integ_user2 присоединился к комнате."
            # или сообщение от самого себя, если broadcast идет и отправителю
            msg_after_say1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
            # Если это не сообщение о присоединении, то это эхо "SAY" от самого себя
            if "integ_user2 присоединился".encode('utf-8') not in msg_after_say1:
                 self.assertIn(b"integ_user: Hello from client1", msg_after_say1) # Эхо для отправителя
        except asyncio.TimeoutError:
            self.fail("Клиент 1 не получил подтверждение или сообщение о присоединении после SAY")


        # Клиент 2 должен получить сообщение "SAY" от клиента 1
        chat_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        self.assertIn(b"integ_user: Hello from client1", chat_msg_for_c2)


        # Клиент 2 отправляет сообщение
        writer2.write(b"SAY Hi from client2\n")
        await writer2.drain()

        # Клиент 1 должен получить сообщение от клиента 2
        chat_msg_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        self.assertIn(b"integ_user2: Hi from client2", chat_msg_for_c1)

        # Клиент 2 может получить эхо своего сообщения
        try:
            echo_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
            self.assertIn(b"integ_user2: Hi from client2", echo_msg_for_c2)
        except asyncio.TimeoutError:
            self.fail("Клиент 2 не получил эхо своего сообщения SAY")


        # Закрываем соединения
        writer1.write(b"QUIT\n")
        await writer1.drain()
        writer1.close()
        await writer1.wait_closed()

        writer2.write(b"QUIT\n")
        await writer2.drain()
        writer2.close()
        await writer2.wait_closed()

    async def test_09_game_server_quit_command(self):
        """Тест команды QUIT на игровом сервере."""
        reader, writer = await asyncio.open_connection(HOST, GAME_PORT)

        # Логин
        writer.write(b"LOGIN integ_user integ_pass\n")
        await writer.drain()
        await reader.readuntil(b"\n") # LOGIN_SUCCESS
        await reader.readuntil(b"\n") # "Добро пожаловать..."
        # Может быть сообщение о присоединении, если другие тесты оставили игроков
        # Попробуем прочитать его с таймаутом
        try:
            await asyncio.wait_for(reader.readuntil(b"\n"), timeout=0.5)
        except asyncio.TimeoutError:
            pass # Ничего страшного, если сообщения не было

        # Отправляем QUIT
        writer.write(b"QUIT\n")
        await writer.drain()

        # Сервер должен отправить подтверждение QUIT и закрыть соединение
        try:
            response_quit = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=1.0)
            self.assertIn("SERVER: Вы выходите из комнаты...".encode('utf-8'), response_quit)

            # После QUIT сервер должен закрыть соединение, readuntil должен вернуть пустую строку или ошибку
            # В handle_game_client после команды QUIT writer закрывается.
            # Это приведет к тому, что readuntil на клиенте получит EOF.
            eof_signal = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=1.0)
            self.assertEqual(eof_signal, b"") # Ожидаем EOF

        except asyncio.TimeoutError:
            self.fail("Сервер не ответил на QUIT или не закрыл соединение вовремя.")
        except asyncio.IncompleteReadError:
            # Это ожидаемое поведение, если сервер закрыл соединение после отправки QUIT
            pass
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()


if __name__ == '__main__':
    # Запуск тестов
    # Необходимо убедиться, что серверы запускаются перед тестами и останавливаются после
    # Это делается в setUpClass и tearDownClass
    unittest.main()
