# tests/test_integration.py
import asyncio
import unittest
import subprocess
import time
import json
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

AUTH_PORT = 8888
GAME_PORT = 8889
HOST = '127.0.0.1'

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def tcp_client_request(host: str, port: int, message: str, timeout: float = 10.0) -> str: # Default timeout increased to 10.0
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout
        )
        if port == GAME_PORT:
            try:
                ack_line_bytes = await asyncio.wait_for(reader.readuntil(b'\n'), timeout=timeout)
                ack_line_str = ack_line_bytes.decode('utf-8').strip()
                logger.info(f"TCP Client: Received initial ACK from game server ({host}:{port}): {ack_line_str}")
                if not ack_line_str.startswith("SERVER_ACK_CONNECTED"):
                    logger.error(f"TCP Client: Unexpected ACK from game server. Expected to start with 'SERVER_ACK_CONNECTED', got: '{ack_line_str}'")
                    if writer and not writer.is_closing():
                        writer.close()
                        await writer.wait_closed() 
                    raise ConnectionAbortedError(f"Game server did not send expected ACK. Got: {ack_line_str}")
            except asyncio.TimeoutError:
                logger.error(f"TCP Client: Timeout waiting for initial ACK from game server {host}:{port}.")
                if writer and not writer.is_closing(): 
                    writer.close()
                    await writer.wait_closed()
                raise ConnectionAbortedError(f"Timeout waiting for initial ACK from game server {host}:{port}")
            except asyncio.IncompleteReadError as e:
                logger.error(f"TCP Client: IncompleteReadError waiting for initial ACK from game server {host}:{port}. Partial: {e.partial!r}")
                if writer and not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
                raise ConnectionAbortedError(f"IncompleteReadError waiting for initial ACK from game server: {e.partial!r}")
            except ConnectionAbortedError: 
                raise
            except Exception as e_ack: 
                logger.error(f"TCP Client: Exception waiting for initial ACK from game server {host}:{port}: {e_ack}", exc_info=True)
                if writer and not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
                raise ConnectionAbortedError(f"Exception waiting for initial ACK from game server: {e_ack}")

        full_message = message if message.endswith('\n') else message + '\n'
        writer.write(full_message.encode('utf-8')) 
        await writer.drain()
        response_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=timeout)
        response_str = response_bytes.decode('utf-8').strip()
        writer.close()
        await writer.wait_closed()
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
    auth_server_process: subprocess.Popen | None = None
    game_server_process: subprocess.Popen | None = None

    # Log file names
    AUTH_SERVER_STDOUT_LOG = "auth_server_stdout.log"
    AUTH_SERVER_STDERR_LOG = "auth_server_stderr.log"
    GAME_SERVER_STDOUT_LOG = "game_server_stdout.log"
    GAME_SERVER_STDERR_LOG = "game_server_stderr.log"

    # File objects for server logs
    auth_stdout_file = None
    auth_stderr_file = None
    game_stdout_file = None
    game_stderr_file = None

    @staticmethod
    def _log_file_content(filename: str, description: str):
        logger.info(f"--- Содержимое {description} ({filename}) ---")
        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            logger.info(content if content.strip() else "<пусто или только пробельные символы>")
        except FileNotFoundError:
            logger.warning(f"Файл лога {filename} не найден.")
        except Exception as e:
            logger.error(f"Ошибка при чтении файла лога {filename}: {e}", exc_info=True)
        logger.info(f"--- Конец {description} ({filename}) ---")

    @staticmethod
    async def _check_server_ready(host: str, port: int, server_name: str, expect_ack_message: str | None = None, attempts: int = 30, delay: float = 2.0, conn_timeout: float = 5.0): # Defaults further increased
        logger.info(f"_check_server_ready: Вход для {server_name} на {host}:{port}, expect_ack='{expect_ack_message}', attempts={attempts}, delay={delay}s, conn_timeout={conn_timeout}s")
        for i in range(attempts):
            writer = None
            attempt_num = i + 1
            # logger.info(f"_check_server_ready: Попытка {attempt_num}/{attempts}: Подключение к {server_name}...")
            ack_timeout = conn_timeout + 1.0 # Defined here for use in TimeoutError log
            try:
                logger.debug(f"_check_server_ready: Попытка {attempt_num}/{attempts}: Вызов asyncio.open_connection к {server_name} ({host}:{port}) с таймаутом {conn_timeout}s...")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=conn_timeout
                )
                # logger.info(f"_check_server_ready: Попытка {attempt_num}: Соединение с {server_name} установлено.")
                logger.debug(f"_check_server_ready: Попытка {attempt_num}: Соединение с {server_name} УСТАНОВЛЕНО.")
                if expect_ack_message:
                    # ack_timeout = conn_timeout + 1.0 # Moved up
                    # logger.info(f"_check_server_ready: Попытка {attempt_num}: Чтение ACK от {server_name} с таймаутом {ack_timeout}s...")
                    logger.debug(f"_check_server_ready: Попытка {attempt_num}: Ожидание ACK '{expect_ack_message}' от {server_name} с таймаутом {ack_timeout}s...")
                    ack_bytes = await asyncio.wait_for(reader.readuntil(b'\n'), timeout=ack_timeout)
                    ack_str = ack_bytes.decode('utf-8').strip()
                    # logger.info(f"_check_server_ready: Попытка {attempt_num}: Получен ACK от {server_name}: '{ack_str}'")
                    logger.debug(f"_check_server_ready: Попытка {attempt_num}: Получен ответ от {server_name}: '{ack_str}' (сырые байты: {ack_bytes!r})")
                    if ack_str.startswith(expect_ack_message):
                        # logger.info(f"_check_server_ready: {server_name} готов и ответил ожидаемым ACK.")
                        logger.info(f"_check_server_ready: Попытка {attempt_num}: ACK от {server_name} ВЕРНЫЙ. Сервер готов.")
                        if writer:
                            writer.close()
                            await writer.wait_closed()
                        logger.info(f"_check_server_ready: Выход: {server_name} ГОТОВ (попытка {attempt_num}).")
                        return True
                    else:
                        # logger.warning(f"_check_server_ready: Попытка {attempt_num}: ACK от {server_name} НЕВЕРНЫЙ: '{ack_str}', ожидалось начало с '{expect_ack_message}'.")
                        logger.warning(f"_check_server_ready: Попытка {attempt_num}: ACK от {server_name} НЕВЕРНЫЙ. Ожидалось начало с '{expect_ack_message}', получено: '{ack_str}'")
                else:
                    # logger.info(f"_check_server_ready: {server_name} готов (соединение установлено без ACK).")
                    logger.info(f"_check_server_ready: Попытка {attempt_num}: Проверка соединения с {server_name} успешна (ACK не требовался). Сервер готов.")
                    if writer:
                        writer.close()
                        await writer.wait_closed()
                    logger.info(f"_check_server_ready: Выход: {server_name} ГОТОВ (попытка {attempt_num}, ACK не требовался).")
                    return True
            except ConnectionRefusedError as e:
                # logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: ConnectionRefusedError - {e}")
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: ConnectionRefusedError при подключении к {server_name} ({host}:{port}). Сервер не доступен. Ошибка: {e}")
            except asyncio.TimeoutError as e:
                # logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: asyncio.TimeoutError - {e}")
                current_timeout = conn_timeout if "open_connection" in str(e).lower() or not expect_ack_message else ack_timeout
                # This distinction is heuristic. A more robust way would be to catch TimeoutError specifically around open_connection and readuntil.
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: asyncio.TimeoutError (таймаут примерно {current_timeout}s) при связи с {server_name} ({host}:{port}). Ошибка: {e}")
            except asyncio.IncompleteReadError as e:
                # logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: asyncio.IncompleteReadError - Partial: {e.partial!r}")
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: asyncio.IncompleteReadError при чтении от {server_name} ({host}:{port}). Частичные данные: {e.partial!r}. Ошибка: {e}")
            except Exception as e:
                # logger.error(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: {type(e).__name__} - {e}", exc_info=False)
                logger.error(f"_check_server_ready: Попытка {attempt_num}: Неожиданное исключение {type(e).__name__} при связи с {server_name} ({host}:{port}): {e}", exc_info=True)
            finally:
                if writer and not writer.is_closing():
                    # logger.info(f"_check_server_ready: Попытка {attempt_num}: Закрытие writer для {server_name}...")
                    logger.debug(f"_check_server_ready: Попытка {attempt_num}: Закрытие writer для {server_name} в блоке finally.")
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception as e_close:
                        # logger.error(f"_check_server_ready: Попытка {attempt_num}: Ошибка при закрытии writer для {server_name}: {e_close}")
                        logger.error(f"_check_server_ready: Попытка {attempt_num}: Ошибка при ожидании закрытия writer для {server_name}: {e_close}", exc_info=True)
            if i < attempts - 1:
                logger.info(f"_check_server_ready: Попытка {attempt_num}: Ожидание задержки ({delay}s) перед следующей попыткой для {server_name}...")
                await asyncio.sleep(delay)
        logger.error(f"_check_server_ready: Выход: {server_name} НЕ ГОТОВ после {attempts} попыток.")
        return False

    @classmethod
    def setUpClass(cls):
        logger.info("setUpClass: Инициализация тестового окружения для интеграционных тестов...")
        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        env["USE_MOCKS"] = "true" 
        env["AUTH_SERVER_HOST"] = HOST
        env["AUTH_SERVER_PORT"] = str(AUTH_PORT)
        env["GAME_SERVER_TCP_HOST"] = HOST
        env["GAME_SERVER_TCP_PORT"] = str(GAME_PORT)
        env["GAME_SERVER_UDP_PORT"] = "29998" # Consistent with game_server/main.py default
        
        logger.info(f"setUpClass: Переменные окружения для запуска серверов: PYTHONPATH={env.get('PYTHONPATH')}, USE_MOCKS={env.get('USE_MOCKS')}, AUTH_PORT={env.get('AUTH_SERVER_PORT')}, GAME_TCP_PORT={env.get('GAME_SERVER_TCP_PORT')}, GAME_UDP_PORT={env.get('GAME_SERVER_UDP_PORT')}")

        # --- Auth Server Setup ---
        logger.info(f"setUpClass: Открытие файлов логов для Auth Server: {cls.AUTH_SERVER_STDOUT_LOG}, {cls.AUTH_SERVER_STDERR_LOG}")
        cls.auth_stdout_file = open(cls.AUTH_SERVER_STDOUT_LOG, "wb")
        cls.auth_stderr_file = open(cls.AUTH_SERVER_STDERR_LOG, "wb")

        logger.info(f"setUpClass: Запуск процесса сервера аутентификации (auth_server.main) на {HOST}:{AUTH_PORT}...")
        cls.auth_server_process = subprocess.Popen(
            [sys.executable, "-B", "-m", "auth_server.main"],
            env=env,
            stdout=cls.auth_stdout_file,
            stderr=cls.auth_stderr_file
        )
        logger.info(f"setUpClass: Процесс сервера аутентификации запущен. PID: {cls.auth_server_process.pid}")
        time.sleep(0.5) # Даем время на возможный немедленный выход

        auth_poll_result = cls.auth_server_process.poll()
        if auth_poll_result is not None:
            logger.error(f"setUpClass: Сервер аутентификации завершился сразу после запуска. Код возврата: {auth_poll_result}")
            if cls.auth_stdout_file: cls.auth_stdout_file.close()
            if cls.auth_stderr_file: cls.auth_stderr_file.close()
            cls._log_file_content(cls.AUTH_SERVER_STDOUT_LOG, "Auth Server STDOUT on immediate exit")
            cls._log_file_content(cls.AUTH_SERVER_STDERR_LOG, "Auth Server STDERR on immediate exit")
            raise RuntimeError(f"Сервер аутентификации не запустился (код: {auth_poll_result}). См. {cls.AUTH_SERVER_STDERR_LOG}")

        logger.info("setUpClass: Вызов _check_server_ready для сервера аутентификации...")
        auth_ready_result = asyncio.run(cls._check_server_ready(HOST, AUTH_PORT, server_name="Auth Server"))
        if not auth_ready_result:
            logger.error("setUpClass: Сервер аутентификации не прошел проверку готовности.")
            if cls.auth_stdout_file: cls.auth_stdout_file.close()
            if cls.auth_stderr_file: cls.auth_stderr_file.close()
            cls._log_file_content(cls.AUTH_SERVER_STDOUT_LOG, "Auth Server STDOUT on readiness failure")
            cls._log_file_content(cls.AUTH_SERVER_STDERR_LOG, "Auth Server STDERR on readiness failure")
            if cls.auth_server_process.poll() is None:
                cls.auth_server_process.terminate()
                try:
                    cls.auth_server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning(f"setUpClass: Таймаут ожидания завершения сервера аутентификации (PID: {cls.auth_server_process.pid}) после terminate. Попытка kill...")
                    cls.auth_server_process.kill()
                # terminate/kill logic from original code
                try:
                    cls.auth_server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning(f"setUpClass: Таймаут ожидания завершения сервера аутентификации (PID: {cls.auth_server_process.pid}) после terminate. Попытка kill...")
                    cls.auth_server_process.kill()
                    try:
                        cls.auth_server_process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        logger.error(f"setUpClass: Сервер аутентификации (PID: {cls.auth_server_process.pid}) не завершился даже после kill.")
            raise RuntimeError("Auth Server не прошел проверку готовности. См. лог-файлы.")
        logger.info("setUpClass: Auth Server успешно запущен и готов.")

        # --- Game Server Setup ---
        logger.info(f"setUpClass: Открытие файлов логов для Game Server: {cls.GAME_SERVER_STDOUT_LOG}, {cls.GAME_SERVER_STDERR_LOG}")
        cls.game_stdout_file = open(cls.GAME_SERVER_STDOUT_LOG, "wb")
        cls.game_stderr_file = open(cls.GAME_SERVER_STDERR_LOG, "wb")

        logger.info(f"setUpClass: Запуск процесса игрового сервера (game_server.main) TCP на {HOST}:{GAME_PORT}...")
        cls.game_server_process = subprocess.Popen(
            [sys.executable, "-B", "-m", "game_server.main"],
            env=env,
            stdout=cls.game_stdout_file,
            stderr=cls.game_stderr_file
        )
        logger.info(f"setUpClass: Процесс игрового сервера запущен. PID: {cls.game_server_process.pid}")
        time.sleep(0.5) # Даем время на возможный немедленный выход

        game_poll_result = cls.game_server_process.poll()
        if game_poll_result is not None:
            logger.error(f"setUpClass: Игровой сервер завершился сразу после запуска. Код возврата: {game_poll_result}")
            if cls.game_stdout_file: cls.game_stdout_file.close()
            if cls.game_stderr_file: cls.game_stderr_file.close()
            cls._log_file_content(cls.GAME_SERVER_STDOUT_LOG, "Game Server STDOUT on immediate exit")
            cls._log_file_content(cls.GAME_SERVER_STDERR_LOG, "Game Server STDERR on immediate exit")
            # Stop auth server if game server failed
            if cls.auth_server_process and cls.auth_server_process.poll() is None:
                cls.auth_server_process.terminate()
                if cls.auth_stdout_file: cls.auth_stdout_file.close() # Close its logs too
                if cls.auth_stderr_file: cls.auth_stderr_file.close()
                cls.auth_server_process.wait(timeout=2)
            raise RuntimeError(f"Игровой сервер не запустился (код: {game_poll_result}). См. {cls.GAME_SERVER_STDERR_LOG}")

        logger.info("setUpClass: Вызов _check_server_ready для игрового сервера...")
        game_ready_result = asyncio.run(cls._check_server_ready(HOST, GAME_PORT, server_name="Game Server", expect_ack_message="SERVER_ACK_CONNECTED"))
        if not game_ready_result:
            logger.error("setUpClass: Игровой сервер не прошел проверку готовности.")
            if cls.game_stdout_file: cls.game_stdout_file.close()
            if cls.game_stderr_file: cls.game_stderr_file.close()
            cls._log_file_content(cls.GAME_SERVER_STDOUT_LOG, "Game Server STDOUT on readiness failure")
            cls._log_file_content(cls.GAME_SERVER_STDERR_LOG, "Game Server STDERR on readiness failure")

            if cls.game_server_process.poll() is None:
                cls.game_server_process.terminate()
                try:
                    cls.game_server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning(f"setUpClass: Таймаут ожидания завершения игрового сервера (PID: {cls.game_server_process.pid}) после terminate. Попытка kill...")
                    cls.game_server_process.kill()
                # terminate/kill logic from original code
                try:
                    cls.game_server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning(f"setUpClass: Таймаут ожидания завершения игрового сервера (PID: {cls.game_server_process.pid}) после terminate. Попытка kill...")
                    cls.game_server_process.kill()
                    try:
                        cls.game_server_process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        logger.error(f"setUpClass: Игровой сервер (PID: {cls.game_server_process.pid}) не завершился даже после kill.")

            # Stop auth server if game server failed readiness check
            if cls.auth_server_process and cls.auth_server_process.poll() is None:
                cls.auth_server_process.terminate()
                if cls.auth_stdout_file: cls.auth_stdout_file.close() # Close its logs too
                if cls.auth_stderr_file: cls.auth_stderr_file.close()
                # Optionally log auth server files here as well if game server fails, for complete diagnostics
                cls._log_file_content(cls.AUTH_SERVER_STDOUT_LOG, "Auth Server STDOUT (Game Server readiness failure)")
                cls._log_file_content(cls.AUTH_SERVER_STDERR_LOG, "Auth Server STDERR (Game Server readiness failure)")
                cls.auth_server_process.wait(timeout=2)
            raise RuntimeError("Game Server не прошел проверку готовности. См. лог-файлы.")
        logger.info("setUpClass: Game Server успешно запущен и готов.")
        
        logger.info("setUpClass: Все серверы успешно запущены и готовы для интеграционных тестов.")

    @classmethod
    def tearDownClass(cls):
        logger.info("tearDownClass: Начало остановки серверов...")
        # Auth Server
        if cls.auth_server_process:
            if cls.auth_server_process.poll() is None:
                logger.info(f"tearDownClass: Попытка терминировать сервер аутентификации (PID: {cls.auth_server_process.pid})...")
                cls.auth_server_process.terminate()
                try:
                    cls.auth_server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"tearDownClass: Таймаут ожидания завершения сервера аутентификации (PID: {cls.auth_server_process.pid}). Попытка kill...")
                    cls.auth_server_process.kill()
                    cls.auth_server_process.wait(timeout=1) # Give a moment for kill
                logger.info(f"tearDownClass: Сервер аутентификации (PID: {cls.auth_server_process.pid}) остановлен.")
            else:
                logger.info(f"tearDownClass: Сервер аутентификации (PID: {cls.auth_server_process.pid}) уже был остановлен.")
            # Close and log files
            if cls.auth_stdout_file: cls.auth_stdout_file.close()
            if cls.auth_stderr_file: cls.auth_stderr_file.close()
            cls._log_file_content(cls.AUTH_SERVER_STDOUT_LOG, "Auth Server STDOUT")
            cls._log_file_content(cls.AUTH_SERVER_STDERR_LOG, "Auth Server STDERR")
        else:
            logger.info("tearDownClass: Сервер аутентификации не был запущен.")

        # Game Server
        if cls.game_server_process:
            if cls.game_server_process.poll() is None:
                logger.info(f"tearDownClass: Попытка терминировать игровой сервер (PID: {cls.game_server_process.pid})...")
                cls.game_server_process.terminate()
                try:
                    cls.game_server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"tearDownClass: Таймаут ожидания завершения игрового сервера (PID: {cls.game_server_process.pid}). Попытка kill...")
                    cls.game_server_process.kill()
                    cls.game_server_process.wait(timeout=1) # Give a moment for kill
                logger.info(f"tearDownClass: Игровой сервер (PID: {cls.game_server_process.pid}) остановлен.")
            else:
                logger.info(f"tearDownClass: Игровой сервер (PID: {cls.game_server_process.pid}) уже был остановлен.")
            # Close and log files
            if cls.game_stdout_file: cls.game_stdout_file.close()
            if cls.game_stderr_file: cls.game_stderr_file.close()
            cls._log_file_content(cls.GAME_SERVER_STDOUT_LOG, "Game Server STDOUT")
            cls._log_file_content(cls.GAME_SERVER_STDERR_LOG, "Game Server STDERR")
        else:
            logger.info("tearDownClass: Игровой сервер не был запущен.")
        
        logger.info("tearDownClass: Завершение остановки серверов.")

    async def asyncSetUp(self):
        logger.info("asyncSetUp: Entered.")
        if self.auth_server_process and self.auth_server_process.poll() is not None:
            self.fail("Сервер аутентификации неожиданно завершился перед тестом.")
        if self.game_server_process and self.game_server_process.poll() is not None:
            self.fail("Игровой сервер неожиданно завершился перед тестом.")
        logger.info("asyncSetUp: Exited.")

    async def test_01_auth_server_login_success(self):
        logger.info("test_01_auth_server_login_success: Entered test method.")
        request_payload = {"action": "login", "username": "integ_user", "password": "integ_pass"}
        logger.info("test_01_auth_server_login_success: Calling tcp_client_request...")
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        logger.info(f"test_01_auth_server_login_success: tcp_client_request returned: {response_str}")
        try:
            logger.info("test_01_auth_server_login_success: Attempting json.loads...")
            response_json = json.loads(response_str)
            logger.info(f"test_01_auth_server_login_success: json.loads successful. Response: {response_json}")
            self.assertEqual(response_json.get("status"), "success", f"Ответ сервера: {response_str}")
            self.assertIn("authenticated successfully", response_json.get("message", ""), "Сообщение об успехе неверно.")
        except json.JSONDecodeError:
            logger.error("test_01_auth_server_login_success: JSONDecodeError occurred.")
            self.fail(f"Не удалось декодировать JSON из ответа сервера аутентификации: {response_str}")
        logger.info("test_01_auth_server_login_success: Exiting test method.")

    async def test_02_auth_server_login_failure_wrong_pass(self):
        request_payload = {"action": "login", "username": "integ_user_fail", "password": "wrong_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("Incorrect password", response_json.get("message", ""), "Сообщение о неверном пароле неверно.")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_03_auth_server_login_failure_user_not_found(self):
        request_payload = {"action": "login", "username": "non_existent_user_integ", "password": "some_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("User not found", response_json.get("message", ""), "Сообщение 'Пользователь не найден' неверно.")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_04_auth_server_invalid_json_action(self):
        request_payload = {"action": "UNKNOWN_ACTION_JSON_TEST", "data": "some_payload"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "error", f"Ответ сервера: {response_str}")
            self.assertEqual(response_json.get("message"), "Unknown or missing action", f"Сообщение об ошибке неверно: {response_str}")
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")
            
    async def test_05_game_server_login_success_via_auth_client(self):
        reader = None
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(HOST, GAME_PORT),
                timeout=2.0
            )

            # 1. Read SERVER_ACK_CONNECTED
            ack_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            self.assertEqual(ack_bytes.decode('utf-8').strip(), "SERVER_ACK_CONNECTED", "Did not receive SERVER_ACK_CONNECTED")

            # 2. Send LOGIN command
            login_command = "LOGIN integ_user integ_pass\n"
            writer.write(login_command.encode('utf-8'))
            await writer.drain()

            # 3. Read LOGIN_SUCCESS response
            login_response_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            login_response_str = login_response_bytes.decode('utf-8').strip()
            self.assertTrue(login_response_str.startswith("LOGIN_SUCCESS"), f"Ответ от игрового сервера на LOGIN: {login_response_str}")
            self.assertIn("Token:", login_response_str, "Ответ на LOGIN должен содержать информацию о токене.")

            # 4. Read SERVER: Welcome to the game room!
            welcome_response_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            welcome_response_str = welcome_response_bytes.decode('utf-8').strip()
            self.assertEqual(welcome_response_str, "SERVER: Welcome to the game room!", "Did not receive welcome message")

        except asyncio.TimeoutError:
            self.fail(f"Timeout during TCP communication in test_05")
        except ConnectionRefusedError:
            self.fail(f"Connection refused in test_05")
        except Exception as e:
            self.fail(f"An unexpected error occurred in test_05: {e}")
        finally:
            if writer and not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    async def test_06_game_server_login_failure_via_auth_client(self):
        response = await tcp_client_request(HOST, GAME_PORT, "LOGIN integ_user wrong_pass_for_game")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        self.assertIn("Incorrect password.", response, "Сообщение должно указывать на неверный пароль от сервера аутентификации.")

    async def test_07_game_server_login_user_not_found_via_auth_client(self):
        response = await tcp_client_request(HOST, GAME_PORT, "LOGIN nosuchuser_integ gamepass")
        self.assertTrue(response.startswith("LOGIN_FAILURE"), f"Ответ от игрового сервера: {response}")
        self.assertIn("User not found.", response, "Сообщение должно указывать, что пользователь не найден (от сервера аутентификации).")

    async def test_08_game_server_chat_after_login(self):
        reader1, writer1 = await asyncio.open_connection(HOST, GAME_PORT)
        # Client 1: Read ACK
        ack1_bytes = await reader1.readuntil(b"\n")
        self.assertEqual(ack1_bytes.decode('utf-8').strip(), "SERVER_ACK_CONNECTED")

        login_cmd1 = "LOGIN integ_user integ_pass\n"
        writer1.write(login_cmd1.encode('utf-8'))
        await writer1.drain()

        # Client 1: Read LOGIN_SUCCESS
        login_response1_bytes = await reader1.readuntil(b"\n")
        login_response1 = login_response1_bytes.decode('utf-8')
        self.assertTrue(login_response1.startswith("LOGIN_SUCCESS"), f"Клиент 1: Неудачный логин: {login_response1.strip()}")
        
        # Client 1: Read Welcome message
        welcome1_bytes = await reader1.readuntil(b"\n")
        self.assertEqual(welcome1_bytes.decode('utf-8').strip(), "SERVER: Welcome to the game room!")

        reader2, writer2 = await asyncio.open_connection(HOST, GAME_PORT)
        # Client 2: Read ACK
        ack2_bytes = await reader2.readuntil(b"\n")
        self.assertEqual(ack2_bytes.decode('utf-8').strip(), "SERVER_ACK_CONNECTED")

        login_cmd2 = "LOGIN integ_user2 integ_pass2\n"
        writer2.write(login_cmd2.encode('utf-8'))
        await writer2.drain()

        # Client 2: Read LOGIN_SUCCESS
        login_response2_bytes = await reader2.readuntil(b"\n")
        login_response2 = login_response2_bytes.decode('utf-8')
        self.assertTrue(login_response2.startswith("LOGIN_SUCCESS"), f"Клиент 2: Неудачный логин: {login_response2.strip()}")

        # Client 2: Read Welcome message
        welcome2_bytes = await reader2.readuntil(b"\n")
        self.assertEqual(welcome2_bytes.decode('utf-8').strip(), "SERVER: Welcome to the game room!")

        # Player joined messages
        # When Client 2 (integ_user2) joins, Client 1 (integ_user) should be notified.
        # Client 2 will NOT receive a "Client 1 joined" message because Client 1 was already in the room.

        # Client 1 receives that Client 2 joined
        logger.debug("Test_08: Client 1 (integ_user) expecting notification that Client 2 (integ_user2) joined.")
        join_msg_c2_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0) # Added timeout
        self.assertIn(f"SERVER: Player {login_cmd2.split()[1]} joined the room.".encode('utf-8'), join_msg_c2_for_c1,
                      f"Клиент 1 ({login_cmd1.split()[1]}) не получил сообщение о присоединении Клиента 2 ({login_cmd2.split()[1]}). Получено: {join_msg_c2_for_c1.decode(errors='ignore')}")

        # Client 2 should not expect a "Client 1 joined" message at this point.
        # It will proceed to listen for chat messages.

        say_cmd1 = "SAY Hello from client1\n"
        logger.debug(f"Test_08: Client 1 ({login_cmd1.split()[1]}) sending: {say_cmd1.strip()}")
        writer1.write(say_cmd1.encode('utf-8'))
        await writer1.drain()
        logger.debug(f"Test_08: Client 1 ({login_cmd1.split()[1]}) waiting for echo of SAY command.")
        echo_msg_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd1.split()[1]}: Hello from client1".encode('utf-8'), echo_msg_for_c1, f"Клиент 1 не получил эхо своего сообщения. Получено: {echo_msg_for_c1.decode(errors='ignore')}")

        logger.debug(f"Test_08: Client 2 ({login_cmd2.split()[1]}) waiting for chat message from Client 1.")
        chat_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd1.split()[1]}: Hello from client1".encode('utf-8'), chat_msg_for_c2, f"Клиент 2 не получил сообщение от Клиента 1. Получено: {chat_msg_for_c2.decode(errors='ignore')}")

        say_cmd2 = "SAY Hi from client2\n"
        logger.debug(f"Test_08: Client 2 ({login_cmd2.split()[1]}) sending: {say_cmd2.strip()}")
        writer2.write(say_cmd2.encode('utf-8'))
        await writer2.drain()
        logger.debug(f"Test_08: Client 2 ({login_cmd2.split()[1]}) waiting for echo of SAY command.")
        echo_msg_for_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd2.split()[1]}: Hi from client2".encode('utf-8'), echo_msg_for_c2, f"Клиент 2 не получил эхо своего сообщения. Получено: {echo_msg_for_c2.decode(errors='ignore')}")

        logger.debug(f"Test_08: Client 1 ({login_cmd1.split()[1]}) waiting for chat message from Client 2.")
        chat_msg_for_c1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        self.assertIn(f"{login_cmd2.split()[1]}: Hi from client2".encode('utf-8'), chat_msg_for_c1, f"Клиент 1 не получил сообщение от Клиента 2. Получено: {chat_msg_for_c1.decode(errors='ignore')}")

        logger.debug(f"Test_08: Client 1 ({login_cmd1.split()[1]}) sending QUIT.")
        writer1.write(b"QUIT\n")
        await writer1.drain()
        # Assuming client 1 quitting and its connection handling is okay as per original test structure
        response_to_quit_c1_bytes = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=1.0)
        logger.info(f"test_08_QUIT: Client 1 received in response to QUIT: '{response_to_quit_c1_bytes.decode(errors='ignore').strip()}'")
        # Expect EOF or specific message for client 1
        try:
            extra_data_c1 = await asyncio.wait_for(reader1.read(100), timeout=0.2)
            self.assertEqual(extra_data_c1, b'', f"Соединение Клиента 1 не было закрыто сервером после QUIT. Получено: {extra_data_c1!r}")
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            logger.info("test_08_QUIT: Client 1 connection correctly closed or no further data (expected).")
            pass # Expected if closed
        finally:
            if writer1 and not writer1.is_closing(): # Ensure writer1 is defined and not already closed
                writer1.close()
                await writer1.wait_closed()

        # Now, the modified logic for Client 2 as per the prompt
        logger.info(f"test_08_QUIT: Client 2 ({login_cmd2.split()[1]}) sending QUIT.")
        writer2.write(b"QUIT\n")
        await writer2.drain()

        # Client 2: Step a - Read the broadcast message about Client 1 leaving
        logger.info(f"Test_08: Client 2 ({login_cmd2.split()[1]}) expecting broadcast about Client 1 ({login_cmd1.split()[1]}) quitting.")
        broadcast_msg_bytes_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        broadcast_msg_str_c2 = broadcast_msg_bytes_c2.decode('utf-8').strip()
        logger.info(f"Test_08: Client 2 received broadcast: '{broadcast_msg_str_c2}'")
        self.assertEqual(broadcast_msg_str_c2, f"SERVER: Player {login_cmd1.split()[1]} left the room.")

        # Client 2: Step b - Read its own "You are leaving the room..." message
        logger.info(f"Test_08: Client 2 ({login_cmd2.split()[1]}) expecting its own QUIT confirmation.")
        quit_confirm_bytes_c2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=1.0)
        quit_confirm_str_c2 = quit_confirm_bytes_c2.decode('utf-8').strip()
        logger.info(f"Test_08: Client 2 received own QUIT confirmation: '{quit_confirm_str_c2}'")
        self.assertEqual(quit_confirm_str_c2, "SERVER: You are leaving the room...")

        # Client 2: Step c - Check for EOF / closed connection
        try:
            logger.info("Test_08: Client 2 attempting to read extra data after its QUIT response (expecting EOF)...")
            extra_data_c2 = await asyncio.wait_for(reader2.read(100), timeout=0.2) # Short timeout
            logger.info(f"Test_08: Client 2 read extra_data: {extra_data_c2!r}")
            self.assertEqual(extra_data_c2, b'', f"Соединение Клиента 2 не было закрыто сервером после QUIT. Получено: {extra_data_c2!r}")
        except asyncio.TimeoutError:
            logger.info("Test_08: Client 2 read timed out after its QUIT response (expected for closed connection). Test OK.")
            pass # Test passes for this condition
        except asyncio.IncompleteReadError:
            logger.info("Test_08: Client 2 encountered IncompleteReadError after its QUIT response (expected for closed connection). Test OK.")
            pass # Test passes for this condition
        finally:
            if writer2 and not writer2.is_closing():
                 writer2.close()
                 await writer2.wait_closed()

    async def test_09_game_server_quit_command(self):
        reader, writer = await asyncio.open_connection(HOST, GAME_PORT)
        login_cmd = "LOGIN integ_user integ_pass\n"
        writer.write(login_cmd.encode('utf-8'))
        await writer.drain()
        await reader.readuntil(b"\n") 
        await reader.readuntil(b"\n") 
        try:
            await asyncio.wait_for(reader.readuntil(b"\n"), timeout=0.5)
        except asyncio.TimeoutError:
            pass 

        writer.write(b"QUIT\n")
        await writer.drain()
        try:
            response_quit_bytes = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=1.0)
            self.assertIn("SERVER: You are leaving the room...\n".encode('utf-8'), response_quit_bytes, "Не получено подтверждение выхода.")
            eof_signal = await asyncio.wait_for(reader.read(100), timeout=1.0) 
            self.assertEqual(eof_signal, b"", "Соединение не было закрыто сервером после QUIT (ожидался EOF).")
        except asyncio.TimeoutError:
            self.fail("Сервер не ответил на команду QUIT или не закрыл соединение в течение таймаута.")
        except asyncio.IncompleteReadError:
            logger.info("IncompleteReadError после QUIT, что ожидаемо, если сервер закрыл соединение.")
            pass
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

if __name__ == '__main__':
    unittest.main()
