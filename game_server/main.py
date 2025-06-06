# game_server/main.py
import sys # Ensure sys is imported first if using sys.stderr
# print(f"[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.", flush=True, file=sys.stderr) # Keep this commented for cleaner logs

import asyncio
import logging
import socket
import os
import tempfile # For setup_file_logging
import functools # For functools.partial in TCP server setup
import time # For any time-related operations if needed (though not directly in restored logic)
import threading # For potential metrics/consumer threads (though they are commented out)

# Local module imports for full functionality
from .udp_handler import GameUDPProtocol
from .tcp_handler import handle_game_client
from .game_logic import GameRoom
from .auth_client import AuthClient
from .session_manager import SessionManager
from .tank_pool import TankPool
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Metrics might be used by commented out code
from prometheus_client import start_http_server # For commented out metrics server

# Глобальный логгер для этого модуля, настраивается в __main__
# Примечание: logging.getLogger(__name__) должен вызываться ПОСЛЕ logging.basicConfig
# Пока что мы определяем его здесь, а basicConfig в __main__ настроит корневой логгер,
# от которого этот логгер будет наследоваться.
logger = logging.getLogger(__name__)

# Заглушка для функций метрик (закомментировано, но структура сохранена)
# def update_metrics():
#     pass
# def metrics_updater_loop():
#     pass
# def start_metrics_server():
#     pass

async def start_game_server(session_manager: SessionManager, tank_pool: TankPool):
    """
    Основная асинхронная функция для запуска UDP и TCP серверов игры.
    Настраивает обработчики, игровую комнату и клиент аутентификации.
    """
    loop = asyncio.get_running_loop()

    # Настройка UDP-сервера
    udp_host = os.getenv('GAME_SERVER_UDP_HOST', '0.0.0.0') # Обычно 0.0.0.0 для сервера
    udp_port_str = os.getenv("GAME_SERVER_UDP_PORT", "29998")
    try:
        udp_port = int(udp_port_str)
        logger.info(f"Game UDP server configured for {udp_host}:{udp_port} (from GAME_SERVER_UDP_PORT or default).")
    except ValueError:
        default_udp_port = 29998
        logger.warning(f"Invalid value for GAME_SERVER_UDP_PORT ('{udp_port_str}'). Using default UDP port {default_udp_port}.")
        udp_port = default_udp_port

    transport_udp = None # Инициализируем, чтобы было определено для блока finally
    protocol_udp = None # Также инициализируем protocol_udp

    max_retries = 5
    retry_delay = 2  # секунды
    udp_sock = None # Инициализируем udp_sock вне блока try для доступа в except/finally при необходимости

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}: Creating and configuring UDP socket for {udp_host}:{udp_port}...")
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.info(f"Attempt {attempt + 1}/{max_retries}: SO_REUSEADDR set for UDP socket.")

            if sys.platform == "win32": # pragma: no cover
                try:
                    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    logger.info(f"Attempt {attempt + 1}/{max_retries}: Successfully set SO_EXCLUSIVEADDRUSE for UDP socket on Windows.")
                except OSError as e_exclusive:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: Failed to set SO_EXCLUSIVEADDRUSE for UDP socket on Windows: {e_exclusive}. Proceeding without it.")

            logger.info(f"Attempt {attempt + 1}/{max_retries}: Binding UDP socket to {udp_host}:{udp_port}...")
            udp_sock.bind((udp_host, udp_port))
            logger.info(f"Attempt {attempt + 1}/{max_retries}: UDP socket bound successfully to {udp_host}:{udp_port}.")

            logger.info(f"Attempt {attempt + 1}/{max_retries}: Creating datagram endpoint...")
            transport_udp, protocol_udp = await loop.create_datagram_endpoint(
                lambda: GameUDPProtocol(session_manager=session_manager, tank_pool=tank_pool),
                sock=udp_sock  # Используем предварительно настроенный и привязанный сокет
            )
            logger.info(f"Game UDP server started successfully on attempt {attempt + 1}/{max_retries}, listening on {transport_udp.get_extra_info('sockname')}.")
            break  # Выход из цикла при успехе

        except OSError as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to start UDP server on {udp_host}:{udp_port}: {e}")
            if udp_sock:
                udp_sock.close()
                logger.debug(f"Attempt {attempt + 1}/{max_retries}: Closed UDP socket after error.")

            if attempt == max_retries - 1:
                logger.critical(f"All {max_retries} attempts to start UDP server on {udp_host}:{udp_port} failed. Last error: {e}", exc_info=True)
                raise  # Повторно вызываем последнее исключение
            else:
                logger.info(f"Retrying UDP server setup for {udp_host}:{udp_port} in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
        except Exception as e_general: # Перехват любых других неожиданных ошибок во время настройки
            logger.critical(f"Unexpected error during UDP setup attempt {attempt + 1}/{max_retries} for {udp_host}:{udp_port}: {e_general}", exc_info=True)
            if udp_sock:
                udp_sock.close() # Убедимся, что сокет закрыт и при других исключениях
            raise # Повторно вызываем для остановки запуска сервера

    if not transport_udp: # Эта проверка больше для подстраховки
        logger.critical(f"UDP server setup failed for {udp_host}:{udp_port} after all retries. Transport is None.") # pragma: no cover
        raise RuntimeError(f"UDP server could not be initialized for {udp_host}:{udp_port}.") # pragma: no cover

    # Настройка TCP-сервера и AuthClient
    game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
    game_tcp_port_str = os.getenv('GAME_SERVER_TCP_PORT', '8889')
    try:
        game_tcp_port = int(game_tcp_port_str)
        logger.info(f"Game TCP server configured for {game_tcp_host}:{game_tcp_port} (from GAME_SERVER_TCP_PORT or default).")
    except ValueError:
        default_tcp_port = 8889
        logger.warning(f"Invalid value for GAME_SERVER_TCP_PORT ('{game_tcp_port_str}'). Using default TCP port {default_tcp_port}.")
        game_tcp_port = default_tcp_port

    auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
    auth_server_port_str = os.getenv('AUTH_SERVER_PORT', "8888")
    try:
        auth_server_port = int(auth_server_port_str)
    except ValueError:
        default_auth_port = 8888
        logger.warning(f"Invalid value for AUTH_SERVER_PORT ('{auth_server_port_str}'). Using default Auth Server port {default_auth_port}.")
        auth_server_port = default_auth_port

    logger.info(f"AuthClient will connect to Auth Server at {auth_server_host}:{auth_server_port}.")

    tcp_server = None # Инициализируем, чтобы было определено для блока finally
    try:
        logger.debug("Initializing AuthClient...")
        auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
        logger.debug("AuthClient initialized.")

        logger.debug("Initializing GameRoom...")
        game_room = GameRoom(auth_client=auth_client)
        logger.debug("GameRoom initialized.")

        tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
        logger.debug(f"Attempting to start TCP server on {game_tcp_host}:{game_tcp_port}...")

        tcp_server = await asyncio.start_server(
            tcp_server_handler,
            game_tcp_host,
            game_tcp_port
        )
        logger.info(f"Game TCP server started successfully on {game_tcp_host}:{game_tcp_port}.")

    except OSError as e: # Перехват OSError специально для привязки TCP-сервера
        logger.critical(f"Could not start Game TCP server on {game_tcp_host}:{game_tcp_port}: {e}", exc_info=True)
        # Эта ошибка будет передана в asyncio.run и обработана в __main__
        raise # Повторно вызываем для остановки запуска сервера, если TCP не удался
    except Exception as e_setup: # Перехват других ошибок настройки (например, инициализация AuthClient, GameRoom)
        logger.critical(f"Critical error during server setup (TCP/Auth/GameRoom): {e_setup}", exc_info=True)
        # Эта ошибка будет передана в asyncio.run и обработана в __main__
        raise # Повторно вызываем

    try:
        logger.info("Game server fully initialized. Waiting for termination signal...")
        await asyncio.Event().wait()
    finally:
        logger.info("Stopping game server components...")
        if tcp_server:
            tcp_server.close()
            await tcp_server.wait_closed()
            logger.info("Game TCP server stopped.")
        if transport_udp: # Используем конкретное имя переменной для UDP-транспорта
            transport_udp.close()
            logger.info("Game UDP server stopped.")

if __name__ == '__main__':
    # Сначала настраиваем базовое логирование
    # Формат включает имя модуля, имя функции и номер строки для детальной отладки.
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(), # По умолчанию INFO, если не установлено
        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
        stream=sys.stderr # По умолчанию логируем в stderr
    )

    # Теперь, когда basicConfig выполнен, логгер уровня модуля настроен.
    # Любые операторы print для ULTRA_DEBUG могут быть удалены или оставлены для индикации начального запуска процесса.
    # sys.stdout.write("[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.\n") # Пример прямой записи
    # sys.stderr.write("Test stderr message\n") # Для тестирования захвата stderr

    logger.info("Initializing game server application...")

    logger.debug("Initializing SessionManager...")
    session_manager = SessionManager()
    logger.debug("SessionManager initialized.")

    logger.debug("Initializing TankPool...")
    tank_pool = TankPool(pool_size=int(os.getenv("TANK_POOL_SIZE", 50)))
    logger.debug("TankPool initialized.")

    # Заглушка для запуска сервера метрик (в данный момент закомментировано)
    # try:
    #     logger.info("Attempting to start metrics server...")
    #     start_metrics_server() # Эту функцию нужно будет определить или раскомментировать
    # except Exception as e_metrics:
    #     logger.error(f"Failed to start metrics server: {e_metrics}", exc_info=True)

    # Заглушка для запуска потребителей RabbitMQ (в данный момент закомментировано)
    # try:
    #     logger.info("Attempting to start RabbitMQ consumers...")
    #     # ... (логика запуска потребителей) ...
    # except Exception as e_consumers:
    #     logger.error(f"Failed to start RabbitMQ consumers: {e_consumers}", exc_info=True)

    main_event_loop = None
    try:
        logger.info("Attempting to run main server logic: start_game_server.")
        # Для Python 3.7+ предпочтительнее asyncio.run
        main_event_loop = asyncio.get_event_loop() # Получаем цикл для политик, если нужно, перед запуском
        if sys.platform == "win32" and sys.version_info >= (3, 8): # pragma: no cover
             # Требуется для Windows, если ProactorEventLoop используется по умолчанию и с ним используются конечные точки UDP.
             # SelectorEventLoop обычно более совместим для некоторых использований UDP/подпроцессов в Windows.
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
             logger.info("Windows OS detected: Applied WindowsSelectorEventLoopPolicy for asyncio.") # Обнаружена ОС Windows: применена WindowsSelectorEventLoopPolicy для asyncio.

        asyncio.run(start_game_server(session_manager=session_manager, tank_pool=tank_pool))
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via KeyboardInterrupt.")
        sys.stderr.write("Завершение работы сервера запрошено через KeyboardInterrupt.\n") # Server shutdown requested via KeyboardInterrupt.
    except OSError as e:
        logger.critical(f"CRITICAL: Failed to start server due to OSError (e.g., port binding issue): {e}", exc_info=True)
        sys.stderr.write(f"КРИТИЧЕСКАЯ OSERROR: {e}\n") # CRITICAL OSERROR:
        sys.exit(1)
    except Exception as e:
        logger.critical(f"CRITICAL: Unhandled error in main execution block: {e}", exc_info=True)
        sys.stderr.write(f"КРИТИЧЕСКАЯ ОШИБКА: {e}\n") # CRITICAL ERROR:
        sys.exit(1)
    finally:
        logger.info("Game server application shutting down or has failed to start.")
        # Любая другая необходимая окончательная очистка

    # Это сообщение в идеале не должно быть достигнуто, если сервер работает неопределенно долго через asyncio.Event().wait()
    # если только Event не установлен или не произошла ошибка, обходящая sys.exit.
    logger.info("Game server application main block finished.")
