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

        # Read initial ACK from game server if connected to it
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
    auth_server_log_file = None # Файл для логов сервера аутентификации
    game_server_log_file = None # Файл для логов игрового сервера

    @staticmethod
    async def _check_server_ready(host: str, port: int, server_name: str, expect_ack_message: str | None = None, attempts: int = 5, delay: float = 0.5, conn_timeout: float = 1.0):
        logger.info(f"_check_server_ready: Вход для {server_name} на {host}:{port}, expect_ack='{expect_ack_message}' (attempts={attempts}, delay={delay}, conn_timeout={conn_timeout})")
        for i in range(attempts):
            writer = None
            attempt_num = i + 1
            logger.info(f"_check_server_ready: Попытка {attempt_num}/{attempts}: Подключение к {server_name}...")
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=conn_timeout
                )
                logger.info(f"_check_server_ready: Попытка {attempt_num}: Соединение с {server_name} установлено.")
                if expect_ack_message:
                    logger.info(f"_check_server_ready: Попытка {attempt_num}: Чтение ACK от {server_name}...")
                    # Увеличим таймаут для чтения ACK от игрового сервера, он может быть чуть дольше из-за внутренней инициализации
                    # Используем conn_timeout (базовый) + некий буфер (например, 1.0 или 2.0), а не conn_timeout + 2.0 жестко.
                    # Новый conn_timeout = 1.0, так что ack_timeout будет 1.0 + 1.0 = 2.0
                    ack_timeout = conn_timeout + 1.0 
                    logger.info(f"_check_server_ready: Попытка {attempt_num}: Чтение ACK от {server_name} с таймаутом {ack_timeout}s...")
                    ack_bytes = await asyncio.wait_for(reader.readuntil(b'\n'), timeout=ack_timeout)
                    ack_str = ack_bytes.decode('utf-8').strip()
                    logger.info(f"_check_server_ready: Попытка {attempt_num}: Получен ACK от {server_name}: '{ack_str}'")
                    if ack_str.startswith(expect_ack_message):
                        logger.info(f"_check_server_ready: {server_name} готов и ответил ожидаемым ACK.")
                        if writer:
                            writer.close()
                            await writer.wait_closed()
                        logger.info(f"_check_server_ready: Выход: {server_name} ГОТОВ.")
                        return True
                    else:
                        logger.warning(f"_check_server_ready: Попытка {attempt_num}: ACK от {server_name} НЕВЕРНЫЙ: '{ack_str}', ожидалось начало с '{expect_ack_message}'.")
                else:
                    logger.info(f"_check_server_ready: {server_name} готов (соединение установлено без ACK).")
                    if writer:
                        writer.close()
                        await writer.wait_closed()
                    logger.info(f"_check_server_ready: Выход: {server_name} ГОТОВ.")
                    return True

            except ConnectionRefusedError as e:
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: ConnectionRefusedError - {e}")
            except asyncio.TimeoutError as e:
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: asyncio.TimeoutError - {e}")
            except asyncio.IncompleteReadError as e:
                logger.warning(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: asyncio.IncompleteReadError - Partial: {e.partial!r}")
            except Exception as e:
                logger.error(f"_check_server_ready: Попытка {attempt_num}: Ошибка при подключении/чтении ACK от {server_name}: {type(e).__name__} - {e}", exc_info=False)
            finally:
                if writer and not writer.is_closing():
                    logger.info(f"_check_server_ready: Попытка {attempt_num}: Закрытие writer для {server_name}...")
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception as e_close:
                        logger.error(f"_check_server_ready: Попытка {attempt_num}: Ошибка при закрытии writer для {server_name}: {e_close}")
            
            if i < attempts - 1:
                logger.info(f"_check_server_ready: Попытка {attempt_num}: Ожидание задержки ({delay}s) перед следующей попыткой для {server_name}...")
                await asyncio.sleep(delay)

        logger.error(f"_check_server_ready: Выход: {server_name} НЕ ГОТОВ после {attempts} попыток.")
        return False

    @classmethod
    def setUpClass(cls):
        """
        Метод класса, вызываемый один раз перед запуском всех тестов в классе.
        Запускает сервер аутентификации и игровой сервер.
        Устанавливает переменные окружения, включая USE_MOCKS="true",
        чтобы серверы использовали мок-объекты для внешних зависимостей (Kafka, Redis).
        """
        logger.info("setUpClass: Инициализация тестового окружения для интеграционных тестов...")
        env = os.environ.copy()
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        env["USE_MOCKS"] = "true" 
        env["AUTH_SERVER_HOST"] = HOST
        env["AUTH_SERVER_PORT"] = str(AUTH_PORT)
        env["GAME_SERVER_TCP_HOST"] = HOST
        env["GAME_SERVER_TCP_PORT"] = str(GAME_PORT)
        env["GAME_SERVER_UDP_PORT"] = "9999"
        
        logger.info(f"setUpClass: Переменные окружения для запуска серверов: PYTHONPATH={env.get('PYTHONPATH')}, USE_MOCKS={env.get('USE_MOCKS')}")

        # Открываем файлы для логов серверов используя абсолютные пути
        auth_log_path = os.path.abspath(os.path.join(project_root, "auth_server_integration_stdout.log"))
        game_log_path = os.path.abspath(os.path.join(project_root, "game_server_integration_stdout.log"))
        logger.info(f"setUpClass: Auth server log file path: {auth_log_path}")
        logger.info(f"setUpClass: Game server log file path: {game_log_path}")
        cls.auth_server_log_file = open(auth_log_path, "w", encoding="utf-8")
        cls.game_server_log_file = open(game_log_path, "w", encoding="utf-8")

        # Запуск сервера аутентификации
        logger.info(f"setUpClass: Запуск процесса сервера аутентификации (auth_server.main) на {HOST}:{AUTH_PORT}...")
        cls.auth_server_process = subprocess.Popen(
            [sys.executable, "-m", "auth_server.main"],
            env=env, stdout=cls.auth_server_log_file, stderr=subprocess.STDOUT
        )
        if cls.auth_server_log_file: # Flush after Popen
            cls.auth_server_log_file.flush()
        logger.info(f"setUpClass: Процесс сервера аутентификации запущен. PID: {cls.auth_server_process.pid}")
        logger.info("setUpClass: Небольшая пауза для инициализации сервера аутентификации...")
        time.sleep(0.5) 
        logger.info("setUpClass: Пауза завершена. Проверка состояния процесса сервера аутентификации...")
        
        logger.info("setUpClass: Проверка `auth_server_process.poll()`...")
        auth_poll_result = cls.auth_server_process.poll()
        if auth_poll_result is not None:
            logger.error(f"setUpClass: Сервер аутентификации завершился сразу после запуска. Код возврата: {auth_poll_result}")
            auth_stdout = cls.auth_server_process.stdout.read() if cls.auth_server_process.stdout else ""
            auth_stderr = cls.auth_server_process.stderr.read() if cls.auth_server_process.stderr else ""
            logger.error(f"setUpClass: STDOUT сервера аутентификации: {auth_stdout}")
            logger.error(f"setUpClass: STDERR сервера аутентификации: {auth_stderr}")
            raise RuntimeError(f"Сервер аутентификации не запустился. Код: {auth_poll_result}")

        logger.info("setUpClass: Вызов _check_server_ready для сервера аутентификации...")
        auth_ready_result = asyncio.run(cls._check_server_ready(HOST, AUTH_PORT, server_name="Auth Server"))
        logger.info(f"setUpClass: _check_server_ready для сервера аутентификации завершен. Результат: {auth_ready_result}")
        if not auth_ready_result:
            logger.error("setUpClass: Сервер аутентификации не прошел проверку готовности. Чтение вывода...")
            auth_stdout = cls.auth_server_process.stdout.read() if cls.auth_server_process.stdout else ""
            auth_stderr = cls.auth_server_process.stderr.read() if cls.auth_server_process.stderr else ""
            cls.auth_server_process.terminate() 
            cls.auth_server_process.wait(timeout=2)
            logger.error(f"setUpClass: STDOUT сервера аутентификации: {auth_stdout}")
            logger.error(f"setUpClass: STDERR сервера аутентификации: {auth_stderr}")
            raise RuntimeError("Auth Server не прошел проверку готовности.")
        logger.info("setUpClass: Auth Server успешно запущен и готов.")

        # Запуск игрового сервера
        logger.info(f"setUpClass: Запуск процесса игрового сервера (game_server.main) TCP на {HOST}:{GAME_PORT}...")
        cls.game_server_process = subprocess.Popen(
            [sys.executable, "-m", "game_server.main"],
            env=env, stdout=cls.game_server_log_file, stderr=subprocess.STDOUT
        )
        if cls.game_server_log_file: # Flush after Popen
            cls.game_server_log_file.flush()
        logger.info(f"setUpClass: Процесс игрового сервера запущен. PID: {cls.game_server_process.pid}")
        logger.info("setUpClass: Небольшая пауза для инициализации игрового сервера...")
        time.sleep(0.5)
        logger.info("setUpClass: Пауза завершена. Проверка состояния процесса игрового сервера...")

        logger.info("setUpClass: Проверка `game_server_process.poll()`...")
        game_poll_result = cls.game_server_process.poll()
        if game_poll_result is not None:
            logger.error(f"setUpClass: Игровой сервер завершился сразу после запуска. Код возврата: {game_poll_result}")
            game_stdout = cls.game_server_process.stdout.read() if cls.game_server_process.stdout else ""
            game_stderr = cls.game_server_process.stderr.read() if cls.game_server_process.stderr else ""
            logger.error(f"setUpClass: STDOUT игрового сервера: {game_stdout}")
            logger.error(f"setUpClass: STDERR игрового сервера: {game_stderr}")
            if cls.auth_server_process and cls.auth_server_process.poll() is None:
                cls.auth_server_process.terminate()
                cls.auth_server_process.wait(timeout=2)
            raise RuntimeError(f"Игровой сервер не запустился. Код: {game_poll_result}")

        logger.info("setUpClass: Вызов _check_server_ready для игрового сервера...")
        game_ready_result = asyncio.run(cls._check_server_ready(HOST, GAME_PORT, server_name="Game Server", expect_ack_message="SERVER_ACK_CONNECTED"))
        logger.info(f"setUpClass: _check_server_ready для игрового сервера завершен. Результат: {game_ready_result}")
        if not game_ready_result:
            logger.error("setUpClass: Игровой сервер не прошел проверку готовности. Чтение вывода...")
            game_stdout = cls.game_server_process.stdout.read() if cls.game_server_process.stdout else ""
            game_stderr = cls.game_server_process.stderr.read() if cls.game_server_process.stderr else ""
            cls.game_server_process.terminate() 
            cls.game_server_process.wait(timeout=2)
            if cls.auth_server_process and cls.auth_server_process.poll() is None: 
                cls.auth_server_process.terminate()
                cls.auth_server_process.wait(timeout=2)
            logger.error(f"setUpClass: STDOUT игрового сервера: {game_stdout}")
            logger.error(f"setUpClass: STDERR игрового сервера: {game_stderr}")
            raise RuntimeError("Game Server не прошел проверку готовности.")
        logger.info("setUpClass: Game Server успешно запущен и готов.")
        
        logger.info("setUpClass: Все серверы успешно запущены и готовы для интеграционных тестов.")

    @classmethod
    def tearDownClass(cls):
        """
        Метод класса, вызываемый один раз после выполнения всех тестов в классе.
        Останавливает серверные процессы.
        """
        logger.info("tearDownClass: Начало остановки серверов...")
        if cls.auth_server_process:
            auth_pid = cls.auth_server_process.pid
            logger.info(f"tearDownClass: Попытка терминировать сервер аутентификации (PID: {auth_pid})...")
            cls.auth_server_process.terminate()
            logger.info(f"tearDownClass: Команда terminate() отправлена серверу аутентификации (PID: {auth_pid}).")
            try:
                logger.info(f"tearDownClass: Ожидание завершения сервера аутентификации (PID: {auth_pid}, timeout=5s)...")
                cls.auth_server_process.wait(timeout=5)
                logger.info(f"tearDownClass: Сервер аутентификации (PID: {auth_pid}) завершил ожидание.")
            except subprocess.TimeoutExpired:
                logger.warning(f"tearDownClass: Таймаут ожидания завершения сервера аутентификации (PID: {auth_pid}). Попытка принудительного завершения (kill)...")
                cls.auth_server_process.kill()
                try:
                    cls.auth_server_process.wait(timeout=1)
                    logger.info(f"tearDownClass: Сервер аутентификации (PID: {auth_pid}) завершился после kill.")
                except subprocess.TimeoutExpired:
                    logger.error(f"tearDownClass: Сервер аутентификации (PID: {auth_pid}) не завершился даже после kill.")
                except Exception as e_kill_wait: # Catch other potential errors during wait after kill
                    logger.error(f"tearDownClass: Ошибка при ожидании завершения сервера аутентификации (PID: {auth_pid}) после kill: {e_kill_wait}")
            except Exception as e_wait:
                logger.error(f"tearDownClass: Ошибка при ожидании завершения сервера аутентификации (PID: {auth_pid}): {e_wait}")
            
            logger.info(f"tearDownClass: Чтение stdout/stderr сервера аутентификации (PID: {auth_pid})...")
            # STDOUT/STDERR теперь пишутся в файлы, поэтому прямое чтение здесь не нужно / невозможно как раньше
            # logger.info(f"tearDownClass: Чтение stdout/stderr сервера аутентификации (PID: {auth_pid})...")
            # auth_stdout = cls.auth_server_process.stdout.read().decode(errors='ignore') if cls.auth_server_process.stdout else ""
            # auth_stderr = cls.auth_server_process.stderr.read().decode(errors='ignore') if cls.auth_server_process.stderr else ""
            # logger.debug(f"\n--- STDOUT Сервера Аутентификации (PID: {auth_pid}) ---\n{auth_stdout}")
            # logger.debug(f"--- STDERR Сервера Аутентификации (PID: {auth_pid}) ---\n{auth_stderr}")
            logger.info(f"tearDownClass: Сервер аутентификации (PID: {auth_pid}) остановлен.")
        
        if cls.game_server_process:
            game_pid = cls.game_server_process.pid
            logger.info(f"tearDownClass: Попытка терминировать игровой сервер (PID: {game_pid})...")
            cls.game_server_process.terminate()
            logger.info(f"tearDownClass: Команда terminate() отправлена игровому серверу (PID: {game_pid}).")
            try:
                logger.info(f"tearDownClass: Ожидание завершения игрового сервера (PID: {game_pid}, timeout=5s)...")
                cls.game_server_process.wait(timeout=5)
                logger.info(f"tearDownClass: Игровой сервер (PID: {game_pid}) завершил ожидание.")
            except subprocess.TimeoutExpired:
                logger.warning(f"tearDownClass: Таймаут ожидания завершения игрового сервера (PID: {game_pid}). Попытка принудительного завершения (kill)...")
                cls.game_server_process.kill()
                try:
                    cls.game_server_process.wait(timeout=1)
                    logger.info(f"tearDownClass: Игровой сервер (PID: {game_pid}) завершился после kill.")
                except subprocess.TimeoutExpired:
                    logger.error(f"tearDownClass: Игровой сервер (PID: {game_pid}) не завершился даже после kill.")
                except Exception as e_kill_wait: # Catch other potential errors during wait after kill
                    logger.error(f"tearDownClass: Ошибка при ожидании завершения игрового сервера (PID: {game_pid}) после kill: {e_kill_wait}")
            except Exception as e_wait:
                logger.error(f"tearDownClass: Ошибка при ожидании завершения игрового сервера (PID: {game_pid}): {e_wait}")

            # STDOUT/STDERR теперь пишутся в файлы
            # logger.info(f"tearDownClass: Чтение stdout/stderr игрового сервера (PID: {game_pid})...")
            # game_stdout = cls.game_server_process.stdout.read().decode(errors='ignore') if cls.game_server_process.stdout else ""
            # game_stderr = cls.game_server_process.stderr.read().decode(errors='ignore') if cls.game_server_process.stderr else ""
            # logger.debug(f"\n--- STDOUT Игрового Сервера (PID: {game_pid}) ---\n{game_stdout}")
            # logger.debug(f"--- STDERR Игрового Сервера (PID: {game_pid}) ---\n{game_stderr}")
            logger.info(f"tearDownClass: Игровой сервер (PID: {game_pid}) остановлен.")

        # Закрываем файлы логов сервера
        if hasattr(cls, 'auth_server_log_file') and cls.auth_server_log_file:
            try:
                logger.info("tearDownClass: Flushing auth_server_log_file...")
                cls.auth_server_log_file.flush() # Explicit flush before closing
                cls.auth_server_log_file.close()
                logger.info("tearDownClass: Файл лога сервера аутентификации закрыт.")
            except Exception as e:
                logger.error(f"tearDownClass: Ошибка при закрытии файла лога сервера аутентификации: {e}")
            cls.auth_server_log_file = None # Обнуляем ссылку

        if hasattr(cls, 'game_server_log_file') and cls.game_server_log_file:
            try:
                logger.info("tearDownClass: Flushing game_server_log_file...")
                cls.game_server_log_file.flush() # Explicit flush before closing
                cls.game_server_log_file.close()
                logger.info("tearDownClass: Файл лога игрового сервера закрыт.")
            except Exception as e:
                logger.error(f"tearDownClass: Ошибка при закрытии файла лога игрового сервера: {e}")
            cls.game_server_log_file = None # Обнуляем ссылку
        
        logger.info("tearDownClass: Завершение остановки серверов.")

    async def asyncSetUp(self):
        """
        Асинхронная настройка перед каждым тестом.
        Проверяет, что серверные процессы все еще работают.
        """
        logger.info("asyncSetUp: Entered.")
        if self.auth_server_process and self.auth_server_process.poll() is not None:
            self.fail("Сервер аутентификации неожиданно завершился перед тестом.")
        if self.game_server_process and self.game_server_process.poll() is not None:
            self.fail("Игровой сервер неожиданно завершился перед тестом.")
        logger.info("asyncSetUp: Exited.")

    # --- Тесты для Сервера Аутентификации ---
    async def test_01_auth_server_login_success(self):
        """Тест успешного логина напрямую на сервере аутентификации (JSON)."""
        logger.info("test_01_auth_server_login_success: Entered test method.")
        # Используем пользователя, который должен быть в MOCK_USERS_DB сервера аутентификации.
        # Предполагается, что "integ_user":"integ_pass" существует.
        request_payload = {"action": "login", "username": "integ_user", "password": "integ_pass"}
        logger.info("test_01_auth_server_login_success: Calling tcp_client_request...")
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        logger.info(f"test_01_auth_server_login_success: tcp_client_request returned: {response_str}")
        try:
            logger.info("test_01_auth_server_login_success: Attempting json.loads...")
            response_json = json.loads(response_str)
            logger.info(f"test_01_auth_server_login_success: json.loads successful. Response: {response_json}")
            self.assertEqual(response_json.get("status"), "success", f"Ответ сервера: {response_str}")
            self.assertIn("authenticated successfully", response_json.get("message", ""), "Сообщение об успехе неверно.") # English
        except json.JSONDecodeError:
            logger.error("test_01_auth_server_login_success: JSONDecodeError occurred.")
            self.fail(f"Не удалось декодировать JSON из ответа сервера аутентификации: {response_str}")
        logger.info("test_01_auth_server_login_success: Exiting test method.")

    async def test_02_auth_server_login_failure_wrong_pass(self):
        """Тест неудачного логина (неверный пароль) напрямую на сервере аутентификации (JSON)."""
        request_payload = {"action": "login", "username": "integ_user_fail", "password": "wrong_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("Incorrect password", response_json.get("message", ""), "Сообщение о неверном пароле неверно.") # English
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_03_auth_server_login_failure_user_not_found(self):
        """Тест неудачного логина (пользователь не найден) напрямую на сервере аутентификации (JSON)."""
        request_payload = {"action": "login", "username": "non_existent_user_integ", "password": "some_pass"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "failure", f"Ответ сервера: {response_str}")
            self.assertIn("User not found", response_json.get("message", ""), "Сообщение 'Пользователь не найден' неверно.") # English
        except json.JSONDecodeError:
            self.fail(f"Не удалось декодировать JSON: {response_str}")

    async def test_04_auth_server_invalid_json_action(self): # Переименован для ясности
        """Тест неверного действия (action) в JSON-запросе на сервере аутентификации."""
        request_payload = {"action": "UNKNOWN_ACTION_JSON_TEST", "data": "some_payload"}
        response_str = await tcp_client_request(HOST, AUTH_PORT, json.dumps(request_payload))
        try:
            response_json = json.loads(response_str)
            self.assertEqual(response_json.get("status"), "error", f"Ответ сервера: {response_str}")
            self.assertEqual(response_json.get("message"), "Unknown or missing action", f"Сообщение об ошибке неверно: {response_str}") # English
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
