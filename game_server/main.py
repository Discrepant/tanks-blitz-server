# game_server/main.py
import sys # Ensure sys is imported first if using sys.stderr
print(f"[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.", flush=True, file=sys.stderr) # THIS IS THE TARGET FIRST LINE

# Главный модуль игрового сервера.
# Отвечает за инициализацию и запуск всех компонентов игрового сервера:
# - UDP-сервер для основного игрового взаимодействия.
# - TCP-сервер для управляющих команд и чата.
# - Клиент для сервера аутентификации.
# - Менеджер игровых сессий и пул объектов танков.
# - Потребители сообщений из RabbitMQ для команд игроков и событий матчмейкинга.
# - Сервер метрик Prometheus.

import os
# Removed redundant print: os imported. About to print STARTING...

# --- BEGIN DEBUG PRINTS ---
# import sys # sys is already imported
# import os # os is already imported
# Removed redundant print: STARTING game_server/main.py -- MODIFICATION CHECK 12345 --
print(f"[GAME_SERVER_MAIN_DEBUG] Current sys.path: {sys.path}", flush=True, file=sys.stderr)
print(f"[GAME_SERVER_MAIN_DEBUG] Current os.getcwd(): {os.getcwd()}", flush=True, file=sys.stderr)
print(f"[GAME_SERVER_MAIN_DEBUG] Environ USE_MOCKS: {os.environ.get('USE_MOCKS')}", flush=True, file=sys.stderr)
print(f"[GAME_SERVER_MAIN_DEBUG] Environ PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True, file=sys.stderr)

# try:
#     import core.message_broker_clients
#     print(f"[GAME_SERVER_MAIN_DEBUG] core.message_broker_clients path: {core.message_broker_clients.__file__}", flush=True, file=sys.stderr)
# except ImportError as e_core_mbc:
#     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients: {e_core_mbc}", flush=True, file=sys.stderr)
# except Exception as e_gen_core_mbc:
try:
    import core.message_broker_clients
    print(f"[GAME_SERVER_MAIN_DEBUG] core.message_broker_clients path: {core.message_broker_clients.__file__}", flush=True, file=sys.stderr)
except ImportError as e_core_mbc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients: {e_core_mbc}", flush=True, file=sys.stderr)
except Exception as e_gen_core_mbc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients with GENERAL EXCEPTION: {e_gen_core_mbc}", flush=True, file=sys.stderr)


try:
    import game_server.command_consumer
    print(f"[GAME_SERVER_MAIN_DEBUG] game_server.command_consumer path: {game_server.command_consumer.__file__}", flush=True, file=sys.stderr)
except ImportError as e_gs_cc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import game_server.command_consumer: {e_gs_cc}", flush=True, file=sys.stderr)
except Exception as e_gen_gs_cc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import game_server.command_consumer with GENERAL EXCEPTION: {e_gen_gs_cc}", flush=True, file=sys.stderr)

# --- END DEBUG PRINTS ---

print(f"[GAME_SERVER_MAIN_DEBUG] Minimal imports done. About to import logging.", flush=True, file=sys.stderr)
import logging # Добавляем импорт для логирования
print(f"[GAME_SERVER_MAIN_DEBUG] logging imported. About to import other modules.", flush=True, file=sys.stderr)


# # Устанавливаем уровень DEBUG для всего пакета 'game_server' и добавляем обработчик.
# # Это позволяет детально логировать события внутри этого пакета.
# _gs_logger = logging.getLogger('game_server')
# _gs_logger.setLevel(logging.DEBUG)
# _gs_logger.addHandler(logging.StreamHandler()) 
# # Убеждаемся, что корневой логгер также показывает DEBUG, если basicConfig еще не настроен.
# logging.getLogger().setLevel(logging.DEBUG)

import asyncio
import time # Добавлен для цикла finally в примере, хотя здесь не строго необходим
import functools # Добавлен импорт для использования functools.partial
# import os # Добавлен импорт для работы с переменными окружения -> ALREADY IMPORTED
from .udp_handler import GameUDPProtocol # Обработчик UDP-пакетов
from .tcp_handler import handle_game_client # Обработчик TCP-соединений
from .game_logic import GameRoom # Логика игровой комнаты
from .auth_client import AuthClient # Клиент для сервера аутентификации
from .session_manager import SessionManager # Менеджер игровых сессий
from .tank_pool import TankPool # Пул объектов танков
# from .command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer # Потребители сообщений из RabbitMQ
# from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Метрики Prometheus
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Метрики Prometheus
from prometheus_client import start_http_server # Функция для запуска сервера метрик
import threading # Для запуска компонентов в отдельных потоках

print(f"[GAME_SERVER_MAIN_DEBUG] Core application imports uncommented (including metrics and threading). About to call logging.basicConfig.", flush=True, file=sys.stderr)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')
print(f"[GAME_SERVER_MAIN_DEBUG] logging.basicConfig called.", flush=True, file=sys.stderr)
# Настройка базового логирования.
# Перенесена в блок if __name__ == '__main__', чтобы гарантировать настройку
# до инициализации других логгеров.
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Создаем логгер для текущего модуля
print(f"[GAME_SERVER_MAIN_DEBUG] Main logger acquired.", flush=True, file=sys.stderr)

# Define a file path for integration test logging
INTEGRATION_TEST_LOG_FILE = "/tmp/game_server_integration_test.log"

# Function to set up file logging
def setup_file_logging():
    try:
        # Clear previous log file
        if os.path.exists(INTEGRATION_TEST_LOG_FILE):
            os.remove(INTEGRATION_TEST_LOG_FILE)
        
        file_handler = logging.FileHandler(INTEGRATION_TEST_LOG_FILE)
        # Ensure file_handler also processes DEBUG messages
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler) # Add to root logger to capture all logs
        logging.getLogger().setLevel(logging.DEBUG) # Ensure root logger level is low enough
        # Use logger only after basicConfig and file handler are set up if possible,
        # or ensure this specific logger is configured to output this initial message.
        # For now, this will go to console if root logger is not yet fully configured for file.
        print(f"[GameServerMain] File logging configured to {INTEGRATION_TEST_LOG_FILE}. Root logger level: {logging.getLogger().getEffectiveLevel()}", flush=True, file=sys.stderr)
        logger.info(f"File logging set up to {INTEGRATION_TEST_LOG_FILE}")
    except Exception as e:
        # Fallback to print if logger itself fails during setup
        print(f"[GameServerMain] ERROR setting up file logging: {e}", flush=True, file=sys.stderr)
        logging.error(f"ERROR setting up file logging: {e}", exc_info=True)


# def update_metrics():
#     """
#     Обновляет значения метрик Prometheus на основе текущего состояния
#     SessionManager и TankPool.
#     """
#     # ... (код без изменений) - Этот комментарий указывает, что код ниже не требует перевода, так как он на русском или является кодом.
#     sm = SessionManager() # Получаем экземпляр SessionManager (предполагается Singleton)
#     tp = TankPool()       # Получаем экземпляр TankPool (предполагается Singleton)
#     ACTIVE_SESSIONS.set(len(sm.sessions)) # Устанавливаем метрику активных сессий
#     TANKS_IN_USE.set(len(tp.in_use_tanks)) # Устанавливаем метрику используемых танков


# def metrics_updater_loop():
#     """
#     Асинхронный цикл для периодического обновления метрик Prometheus.
#     Запускается в отдельном потоке.
#     """
#     # ... (код без изменений)
#     # Этот цикл выполняется в отдельном потоке, для него можно настроить свой логгер, если нужно.
#     loop = asyncio.new_event_loop() # Создаем новый цикл событий для этого потока
#     asyncio.set_event_loop(loop)    # Устанавливаем его как текущий для потока
#     async def updater():
#         """Внутренняя асинхронная функция, которая бесконечно обновляет метрики."""
#         while True:
#             update_metrics()
#             await asyncio.sleep(5) # Пауза 5 секунд между обновлениями
#     try: # Добавляем try/finally для корректного закрытия цикла событий
#         loop.run_until_complete(updater())
#     finally:
#         loop.close() # Закрываем цикл событий при завершении


# def start_metrics_server():
#     """
#     Запускает HTTP-сервер для метрик Prometheus и поток для их обновления.
#     """
#     # ... (код без изменений)
#     start_http_server(8001) # Запускаем HTTP-сервер Prometheus на порту 8001
#     logger.info("Prometheus metrics server for Game Server started on port 8001.")
#     # Запускаем цикл обновления метрик в отдельном daemon-потоке
#     metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
#     metrics_loop_thread.setName("MetricsUpdaterThread") # Даем имя потоку для удобства отладки
#     metrics_loop_thread.start()


async def start_game_server(session_manager: SessionManager, tank_pool: TankPool):
#    pass
    """
    Основная асинхронная функция для запуска UDP и TCP серверов игры.
    Настраивает обработчики, игровую комнату и клиент аутентификации.
    """
    host = '0.0.0.0' # Слушаем на всех доступных интерфейсах
    port = 9999      # Порт для UDP-сервера

    # logger.info(f"Starting game UDP server on {host}:{port}...") # Replaced by debug and then specific info
    loop = asyncio.get_running_loop() # Получаем текущий цикл событий

    # SessionManager и TankPool передаются как аргументы.

    # Создаем конечную точку UDP-сервера
    logger.debug(f"Attempting to start UDP server on {host}:{port}...")
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(session_manager=session_manager, tank_pool=tank_pool),
        local_addr=(host, port)
    )

    logger.info(f"Game UDP server started successfully and listening on {transport.get_extra_info('sockname')}.")

    # Запуск TCP-сервера
    game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
    game_tcp_port = int(os.getenv('GAME_SERVER_TCP_PORT', 8889))
    auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
    auth_server_port = int(os.getenv('AUTH_SERVER_PORT', 8888))
    logger.info(f"AuthClient will connect to {auth_server_host}:{auth_server_port}")
    print(f"[GameServerMain_start_game_server] AuthClient target: {auth_server_host}:{auth_server_port}", flush=True, file=sys.stderr)

    try:
        logger.debug("Initializing AuthClient...")
        auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
        logger.debug("AuthClient initialized.")
        print("[GameServerMain_start_game_server] AuthClient initialized.", flush=True, file=sys.stderr)
        
        logger.debug("Initializing GameRoom...")
        game_room = GameRoom(auth_client=auth_client)
        logger.debug("GameRoom initialized.")
        print("[GameServerMain_start_game_server] GameRoom initialized.", flush=True, file=sys.stderr)
        
        tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
        # logger.info("TCP server handler (partial) created.") # This can be debug or removed if too verbose
        logger.debug("TCP server handler (partial) for handle_game_client created.")
        print("[GameServerMain_start_game_server] TCP handler partial created.", flush=True, file=sys.stderr)
        
        logger.debug(f"Attempting to start TCP server on {game_tcp_host}:{game_tcp_port}...")
        # Ensure using asyncio.start_server as per previous fix
        tcp_server = await asyncio.start_server( 
            tcp_server_handler,
            game_tcp_host,
            game_tcp_port
        )
        logger.info(f"Game TCP server started successfully on {game_tcp_host}:{game_tcp_port}.")
        print(f"[GameServerMain_start_game_server] Game TCP server created using asyncio.start_server, listening on {game_tcp_host}:{game_tcp_port}.", flush=True, file=sys.stderr)
        # logger.info("Game Server network listeners (UDP/TCP) are currently COMMEFED OUT for debugging.") # Re-enable listeners

    except Exception as e_setup:
        logger.error(f"Error during TCP server setup: {e_setup}", exc_info=True)
        print(f"[GameServerMain_start_game_server] CRITICAL ERROR during server setup: {e_setup}", flush=True, file=sys.stderr)
        return # Stop if setup fails

    try:
        # logger.info("Game server core logic setup done (network listeners commented out). Entering asyncio.Event().wait().")
        logger.debug("Main server logic initialized. Waiting for termination signal (asyncio.Event().wait()).")
        await asyncio.Event().wait() 
    finally:
        logger.info("Stopping game servers (or what's left of it)...")
        print("[GameServerMain_start_game_server] Stopping game servers in finally block (network listeners were commented out).", flush=True, file=sys.stderr)
        # Остановка TCP-сервера
        if 'tcp_server' in locals() and tcp_server:
            tcp_server.close() # Закрываем сервер
            await tcp_server.wait_closed() # Ожидаем полного закрытия
            logger.info("Game TCP server stopped.")
        # Остановка UDP-сервера
        if 'transport' in locals() and transport:
            transport.close() # Закрываем транспорт UDP
            logger.info("Game UDP server stopped.")

if __name__ == '__main__':
    print(f"[GAME_SERVER_MAIN_DEBUG] Entered if __name__ == '__main__'.", flush=True, file=sys.stderr)
    # Настраиваем логирование здесь, чтобы оно было установлено как можно раньше.
    # logging.basicConfig должен быть вызван до любого logger.XYZ, если используется корневой логгер или логгеры без явной настройки.
    # Поскольку setup_file_logging настраивает корневой логгер, он должен быть первым.
    # А basicConfig должен быть до setup_file_logging, если setup_file_logging использует logger.info для своих сообщений.
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')
    setup_file_logging() # Setup file logging

    logger.info("Starting game server application...")
    print("[GameServerMain] Starting game server application (after logger.info).", flush=True, file=sys.stderr)

    # Инициализация общих экземпляров SessionManager и TankPool.
    logger.debug("Initializing SessionManager...")
    session_manager = SessionManager()
    logger.debug("SessionManager initialized.")

    logger.debug("Initializing TankPool...")
    tank_pool = TankPool(pool_size=50) # Инициализируем с размером пула
    logger.debug("TankPool initialized.")

    # # Запуск сервера метрик Prometheus - ОСТАВИТЬ ЗАКОММЕНТИРОВАННЫМ для этого шага
    # start_metrics_server()

    # # Инициализация и запуск потребителя команд игроков из RabbitMQ - ОСТАВИТЬ ЗАКОММЕНТИРОВАННЫМ
    # logger.info("Initializing PlayerCommandConsumer...")
    # player_command_consumer = PlayerCommandConsumer(session_manager, tank_pool)
    # consumer_thread = threading.Thread(target=player_command_consumer.start_consuming, daemon=True)
    # consumer_thread.setName("PlayerCommandConsumerThread")
    # consumer_thread.start()
    # logger.info("PlayerCommandConsumer started in a separate thread.")

    # # Инициализация и запуск потребителя событий матчмейкинга из RabbitMQ - ОСТАВИТЬ ЗАКОММЕНТИРОВАННЫМ
    # logger.info("Initializing MatchmakingEventConsumer...")
    # matchmaking_event_consumer = MatchmakingEventConsumer(session_manager)
    # matchmaking_consumer_thread = threading.Thread(
    #     target=matchmaking_event_consumer.start_consuming,
    #     daemon=True,
    #     name="MatchmakingEventConsumerThread"
    # )
    # matchmaking_consumer_thread.start()
    # logger.info("MatchmakingEventConsumer started in a separate thread.")

    # Запуск основного игрового сервера
    try:
        # logger.info("Starting asynchronous components of the game server...")
        logger.info("Attempting to run asyncio event loop with start_game_server.")
        asyncio.run(start_game_server(session_manager=session_manager, tank_pool=tank_pool))
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via KeyboardInterrupt.")
    except Exception as e:
        logger.error(f"Unhandled critical error in main execution block: {e}", exc_info=True)
    # finally: # Keep consumers commented for now
    #     logger.info("Attempting to stop consumers...")
    #     # Корректная остановка потребителя команд игроков
    #     if 'player_command_consumer' in locals() and player_command_consumer:
    #         player_command_consumer.stop_consuming()
    #     if 'consumer_thread' in locals() and consumer_thread.is_alive():
    #         logger.info("Waiting for PlayerCommandConsumerThread to complete...")
    #         consumer_thread.join(timeout=5) # Ожидаем завершения потока с таймаутом
    #         if consumer_thread.is_alive():
    #             logger.warning("PlayerCommandConsumerThread did not complete correctly.")
    #         else:
    #             logger.info("PlayerCommandConsumerThread completed successfully.")

    #     # Корректная остановка потребителя событий матчмейкинга
    #     if 'matchmaking_event_consumer' in locals() and matchmaking_event_consumer:
    #         matchmaking_event_consumer.stop_consuming()
    #     if 'matchmaking_consumer_thread' in locals() and matchmaking_consumer_thread.is_alive():
    #         logger.info("Waiting for MatchmakingEventConsumerThread to complete...")
    #         matchmaking_consumer_thread.join(timeout=5) # Ожидаем завершения потока с таймаутом
    #         if matchmaking_consumer_thread.is_alive():
    #             logger.warning("MatchmakingEventConsumerThread did not complete correctly.")
    #         else:
    #             logger.info("MatchmakingEventConsumerThread completed successfully.")
        
    #     logger.info("Game server application completely stopped.")
    print(f"[GAME_SERVER_MAIN_DEBUG] Reached end of if __name__ == '__main__'. Game server should be running or have crashed.", flush=True, file=sys.stderr)
