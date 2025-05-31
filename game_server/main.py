# game_server/main.py
import asyncio
import logging
import os
import sys

# --- Start of new simplified UDP server code ---

class EchoServerProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport
        peername = transport.get_extra_info('sockname')
        # Use logging instead of logger, as logger might not be configured
        # if original basicConfig is also commented out.
        logging.info(f"Simplified UDP Echo server ready on {peername[0]}:{peername[1]}")

    def datagram_received(self, data, addr):
        message = data.decode()
        logging.info(f"Simplified UDP: Received {len(data)} bytes from {addr}: {message!r}")
        logging.info(f"Simplified UDP: Sending {len(data)} bytes back to {addr}: {message!r}")
        self.transport.sendto(data, addr)

    def error_received(self, exc):
        logging.error(f"Simplified UDP: Error received: {exc}", exc_info=True)

    def connection_lost(self, exc):
        logging.info("Simplified UDP: Server connection lost.")

async def start_simplified_udp_server(host, port):
    logging.info(f"Simplified UDP: Attempting to start server on {host}:{port}...")
    loop = asyncio.get_running_loop()
    transport = None # Initialize transport to None
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: EchoServerProtocol(),
            local_addr=(host, port)
        )
        logging.info(f"Simplified UDP: Server started successfully on {host}:{port}.")
        await asyncio.Event().wait()  # Keep server running
    except OSError as e:
        logging.error(f"Simplified UDP: OSError binding to {host}:{port}: {e}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"Simplified UDP: An unexpected error occurred: {e}", exc_info=True)
        raise
    finally:
        if transport: # Check if transport was assigned
            logging.info("Simplified UDP: Closing transport...")
            transport.close()

# --- End of new simplified UDP server code ---

# --- Original code (commented out or to be removed) ---

# import tempfile # Added import
# # Removed redundant print: os imported. About to print STARTING...

# # --- BEGIN DEBUG PRINTS ---
# # import sys # sys is already imported
# # import os # os is already imported
# # Removed redundant print: STARTING game_server/main.py -- MODIFICATION CHECK 12345 --
# # print(f"[GAME_SERVER_MAIN_DEBUG] Current sys.path: {sys.path}", flush=True, file=sys.stderr)
# # print(f"[GAME_SERVER_MAIN_DEBUG] Current os.getcwd(): {os.getcwd()}", flush=True, file=sys.stderr)
# # print(f"[GAME_SERVER_MAIN_DEBUG] Environ USE_MOCKS: {os.environ.get('USE_MOCKS')}", flush=True, file=sys.stderr)
# # print(f"[GAME_SERVER_MAIN_DEBUG] Environ PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True, file=sys.stderr)

# # try:
# #     import core.message_broker_clients
# #     print(f"[GAME_SERVER_MAIN_DEBUG] core.message_broker_clients path: {core.message_broker_clients.__file__}", flush=True, file=sys.stderr)
# # except ImportError as e_core_mbc:
# #     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients: {e_core_mbc}", flush=True, file=sys.stderr)
# # except Exception as e_gen_core_mbc:
# # try:
# #     import core.message_broker_clients
# #     print(f"[GAME_SERVER_MAIN_DEBUG] core.message_broker_clients path: {core.message_broker_clients.__file__}", flush=True, file=sys.stderr)
# # except ImportError as e_core_mbc:
# #     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients: {e_core_mbc}", flush=True, file=sys.stderr)
# # except Exception as e_gen_core_mbc:
# #     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients with GENERAL EXCEPTION: {e_gen_core_mbc}", flush=True, file=sys.stderr)


# # try:
# #     import game_server.command_consumer
# #     print(f"[GAME_SERVER_MAIN_DEBUG] game_server.command_consumer path: {game_server.command_consumer.__file__}", flush=True, file=sys.stderr)
# # except ImportError as e_gs_cc:
# #     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import game_server.command_consumer: {e_gs_cc}", flush=True, file=sys.stderr)
# # except Exception as e_gen_gs_cc:
# #     print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import game_server.command_consumer with GENERAL EXCEPTION: {e_gen_gs_cc}", flush=True, file=sys.stderr)

# # --- END DEBUG PRINTS ---

# # print(f"[GAME_SERVER_MAIN_DEBUG] Minimal imports done. About to import logging.", flush=True, file=sys.stderr)
# # print(f"[GAME_SERVER_MAIN_DEBUG] logging imported. About to import other modules.", flush=True, file=sys.stderr)


# # # Устанавливаем уровень DEBUG для всего пакета 'game_server' и добавляем обработчик.
# # # Это позволяет детально логировать события внутри этого пакета.
# # _gs_logger = logging.getLogger('game_server')
# # _gs_logger.setLevel(logging.DEBUG)
# # _gs_logger.addHandler(logging.StreamHandler())
# # # Убеждаемся, что корневой логгер также показывает DEBUG, если basicConfig еще не настроен.
# # logging.getLogger().setLevel(logging.DEBUG)

# import time # Добавлен для цикла finally в примере, хотя здесь не строго необходим
# import functools # Добавлен импорт для использования functools.partial
# # import os # Добавлен импорт для работы с переменными окружения -> ALREADY IMPORTED
# from .udp_handler import GameUDPProtocol # Обработчик UDP-пакетов
# from .tcp_handler import handle_game_client # Обработчик TCP-соединений
# from .game_logic import GameRoom # Логика игровой комнаты
# from .auth_client import AuthClient # Клиент для сервера аутентификации
# from .session_manager import SessionManager # Менеджер игровых сессий
# from .tank_pool import TankPool # Пул объектов танков
# # from .command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer # Потребители сообщений из RabbitMQ
# # from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Метрики Prometheus
# from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Метрики Prometheus
# from prometheus_client import start_http_server # Функция для запуска сервера метрик
# import threading # Для запуска компонентов в отдельных потоках

# # print(f"[GAME_SERVER_MAIN_DEBUG] Core application imports uncommented (including metrics and threading). About to call logging.basicConfig.", flush=True, file=sys.stderr)
# # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s') # Moved to __main__
# # print(f"[GAME_SERVER_MAIN_DEBUG] logging.basicConfig called.", flush=True, file=sys.stderr)
# # Настройка базового логирования.
# # Перенесена в блок if __name__ == '__main__', чтобы гарантировать настройку
# # до инициализации других логгеров.
# # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# # logger = logging.getLogger(__name__) # Specific logger for this module, configured by basicConfig in __main__
# # print(f"[GAME_SERVER_MAIN_DEBUG] Main logger acquired.", flush=True, file=sys.stderr)

# # Define a file path for integration test logging
# # INTEGRATION_TEST_LOG_FILE = os.path.join(tempfile.gettempdir(), "game_server_integration_test.log") # Changed to be cross-platform

# # Function to set up file logging
# # def setup_file_logging():
# #     try:
# #         # Clear previous log file
# #         try:
# #             if os.path.exists(INTEGRATION_TEST_LOG_FILE):
# #                 os.remove(INTEGRATION_TEST_LOG_FILE)
# #         except (FileNotFoundError, PermissionError) as e:
# #             # Use the module-level logger if available, otherwise logging.warning
# #             # logger should be available as it's defined globally in this module
# #             logging.warning(f"Could not remove old log file {INTEGRATION_TEST_LOG_FILE}: {e}") # Use logging directly

# #         file_handler = logging.FileHandler(INTEGRATION_TEST_LOG_FILE)
# #         # Ensure file_handler also processes DEBUG messages
# #         file_handler.setLevel(logging.DEBUG)
# #         formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
# #         file_handler.setFormatter(formatter)
# #         logging.getLogger().addHandler(file_handler) # Add to root logger to capture all logs
# #         logging.getLogger().setLevel(logging.DEBUG) # Ensure root logger level is low enough
# #         # Use logger only after basicConfig and file handler are set up if possible,
# #         # or ensure this specific logger is configured to output this initial message.
# #         # For now, this will go to console if root logger is not yet fully configured for file.
# #         # print(f"[GameServerMain] File logging configured to {INTEGRATION_TEST_LOG_FILE}. Root logger level: {logging.getLogger().getEffectiveLevel()}", flush=True, file=sys.stderr)
# #         logging.info(f"File logging set up to {INTEGRATION_TEST_LOG_FILE}")
# #     except Exception as e:
# #         # Fallback to print if logger itself fails during setup
# #         # print(f"[GameServerMain] ERROR setting up file logging: {e}", flush=True, file=sys.stderr)
# #         logging.error(f"ERROR setting up file logging: {e}", exc_info=True)


# # def update_metrics():
# #     """
# #     Обновляет значения метрик Prometheus на основе текущего состояния
# #     SessionManager и TankPool.
# #     """
# #     # ... (код без изменений) - Этот комментарий указывает, что код ниже не требует перевода, так как он на русском или является кодом.
# #     sm = SessionManager() # Получаем экземпляр SessionManager (предполагается Singleton)
# #     tp = TankPool()       # Получаем экземпляр TankPool (предполагается Singleton)
# #     ACTIVE_SESSIONS.set(len(sm.sessions)) # Устанавливаем метрику активных сессий
# #     TANKS_IN_USE.set(len(tp.in_use_tanks)) # Устанавливаем метрику используемых танков


# # def metrics_updater_loop():
# #     """
# #     Асинхронный цикл для периодического обновления метрик Prometheus.
# #     Запускается в отдельном потоке.
# #     """
# #     # ... (код без изменений)
# #     # Этот цикл выполняется в отдельном потоке, для него можно настроить свой логгер, если нужно.
# #     loop = asyncio.new_event_loop() # Создаем новый цикл событий для этого потока
# #     asyncio.set_event_loop(loop)    # Устанавливаем его как текущий для потока
# #     async def updater():
# #         """Внутренняя асинхронная функция, которая бесконечно обновляет метрики."""
# #         while True:
# #             update_metrics()
# #             await asyncio.sleep(5) # Пауза 5 секунд между обновлениями
# #     try: # Добавляем try/finally для корректного закрытия цикла событий
# #         loop.run_until_complete(updater())
# #     finally:
# #         loop.close() # Закрываем цикл событий при завершении


# # def start_metrics_server():
# #     """
# #     Запускает HTTP-сервер для метрик Prometheus и поток для их обновления.
# #     """
# #     # ... (код без изменений)
# #     start_http_server(8001) # Запускаем HTTP-сервер Prometheus на порту 8001
# #     logging.info("Prometheus metrics server for Game Server started on port 8001.")
# #     # Запускаем цикл обновления метрик в отдельном daemon-потоке
# #     metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
# #     metrics_loop_thread.setName("MetricsUpdaterThread") # Даем имя потоку для удобства отладки
# #     metrics_loop_thread.start()


# # async def start_game_server(session_manager: SessionManager, tank_pool: TankPool):
# # #    pass
# #     """
# #     Основная асинхронная функция для запуска UDP и TCP серверов игры.
# #     Настраивает обработчики, игровую комнату и клиент аутентификации.
# #     """
# #     host = '0.0.0.0' # Слушаем на всех доступных интерфейсах

# #     # Определение порта для UDP-сервера из переменной окружения или по умолчанию
# #     udp_port_str = os.getenv("GAME_SERVER_UDP_PORT", "29998")
# #     try:
# #         port = int(udp_port_str) # 'port' используется для UDP-сервера
# #         logging.info(f"Game UDP server attempting to use port {port} (from GAME_SERVER_UDP_PORT or default).")
# #     except ValueError:
# #         port = 29998 # Значение по умолчанию, если переменная задана некорректно
# #         logging.warning(f"Invalid value for GAME_SERVER_UDP_PORT ('{udp_port_str}'). Using default UDP port {port}.")

# #     loop = asyncio.get_running_loop() # Получаем текущий цикл событий

# #     # SessionManager и TankPool передаются как аргументы.

# #     # Создаем конечную точку UDP-сервера
# #     logging.info(f"Attempting to bind UDP server to {host}:{port}...") # Added specific INFO log for binding
# #     logging.debug(f"Attempting to start UDP server on {host}:{port}...")
# #     transport, protocol = await loop.create_datagram_endpoint(
# #         lambda: GameUDPProtocol(session_manager=session_manager, tank_pool=tank_pool),
# #         local_addr=(host, port) # 'port' for UDP was defined above
# #     )
# #     logging.info(f"Game UDP server started successfully and listening on {transport.get_extra_info('sockname')}.")
# #     # logger.info("UDP server startup is currently commented out.") # Removed this line


# #     # Запуск TCP-сервера
# #     game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
# #     game_tcp_port = int(os.getenv('GAME_SERVER_TCP_PORT', 8889)) # Assuming this should be int and crash if invalid for game server itself

# #     auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
# #     auth_port_str = os.getenv('AUTH_SERVER_PORT', "8888")
# #     try:
# #         auth_server_port = int(auth_port_str)
# #     except ValueError:
# #         logging.warning(f"Invalid value for AUTH_SERVER_PORT ('{auth_port_str}'). Using default port 8888.")
# #         auth_server_port = 8888

# #     logging.info(f"AuthClient will connect to {auth_server_host}:{auth_server_port}")
# #     # print(f"[GameServerMain_start_game_server] AuthClient target: {auth_server_host}:{auth_server_port}", flush=True, file=sys.stderr)

# #     try:
# #         logging.debug("Initializing AuthClient...")
# #         auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
# #         logging.debug("AuthClient initialized.")
# #         # print("[GameServerMain_start_game_server] AuthClient initialized.", flush=True, file=sys.stderr)

# #         logging.debug("Initializing GameRoom...")
# #         game_room = GameRoom(auth_client=auth_client)
# #         logging.debug("GameRoom initialized.")
# #         # print("[GameServerMain_start_game_server] GameRoom initialized.", flush=True, file=sys.stderr)

# #         tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
# #         # logger.info("TCP server handler (partial) created.") # This can be debug or removed if too verbose
# #         logging.debug("TCP server handler (partial) for handle_game_client created.")
# #         # print("[GameServerMain_start_game_server] TCP handler partial created.", flush=True, file=sys.stderr)

# #         logging.debug(f"Attempting to start TCP server on {game_tcp_host}:{game_tcp_port}...")
# #         # Ensure using asyncio.start_server as per previous fix
# #         tcp_server = await asyncio.start_server(
# #             tcp_server_handler,
# #             game_tcp_host,
# #             game_tcp_port
# #         )
# #         logging.info(f"Game TCP server started successfully on {game_tcp_host}:{game_tcp_port}.")
# #         # print(f"[GameServerMain_start_game_server] Game TCP server created using asyncio.start_server, listening on {game_tcp_host}:{game_tcp_port}.", flush=True, file=sys.stderr)
# #         # logger.info("Game Server network listeners (UDP/TCP) are currently COMMEFED OUT for debugging.") # Re-enable listeners

# #     except Exception as e_setup:
# #         logging.error(f"Error during TCP server setup: {e_setup}", exc_info=True) # Use logging
# #         # print(f"[GameServerMain_start_game_server] CRITICAL ERROR during server setup: {e_setup}", flush=True, file=sys.stderr)
# #         return # Stop if setup fails

# #     try:
# #         # logger.info("Game server core logic setup done (network listeners commented out). Entering asyncio.Event().wait().")
# #         logging.debug("Main server logic initialized. Waiting for termination signal (asyncio.Event().wait()).")
# #         await asyncio.Event().wait()
# #     finally:
# #         logging.info("Stopping game servers (or what's left of it)...")
# #         # print("[GameServerMain_start_game_server] Stopping game servers in finally block (network listeners were commented out).", flush=True, file=sys.stderr)
# #         # Остановка TCP-сервера
# #         if 'tcp_server' in locals() and tcp_server:
# #             tcp_server.close() # Закрываем сервер
# #             await tcp_server.wait_closed() # Ожидаем полного закрытия
# #             logging.info("Game TCP server stopped.")
# #         # Остановка UDP-сервера
# #         if 'transport' in locals() and transport: # 'transport' здесь относится к UDP
# #             transport.close() # Закрываем транспорт UDP
# #             logging.info("Game UDP server stopped.")


if __name__ == '__main__':
    # Базовая настройка логирования для этого упрощенного теста
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s',
                        stream=sys.stderr)

    # Убираем setup_file_logging и старые print-отладки для максимального упрощения
    # print("[GAME_SERVER_MAIN_ULTRA_DEBUG] Process started. sys imported.", flush=True, file=sys.stderr) # Commented out

    target_host = "0.0.0.0"
    udp_port_str = os.getenv("GAME_SERVER_UDP_PORT", "29998")
    try:
        target_udp_port = int(udp_port_str)
    except ValueError:
        logging.warning(f"Simplified UDP: Invalid GAME_SERVER_UDP_PORT '{udp_port_str}', using default 29998.")
        target_udp_port = 29998

    logging.info(f"Simplified UDP: Game server main block attempting to run simplified UDP server on {target_host}:{target_udp_port}.")

    try:
        asyncio.run(start_simplified_udp_server(target_host, target_udp_port))
    except KeyboardInterrupt:
        logging.info("Simplified UDP: Server shutdown requested via KeyboardInterrupt.")
        # print("[GameServerMain] Server shutdown requested via KeyboardInterrupt.", flush=True, file=sys.stderr) # Commented out
    except OSError as e:
        logging.critical(f"Simplified UDP: CRITICAL OSError during asyncio.run (e.g., port binding issue): {e}", exc_info=True)
        sys.stderr.write(f"Simplified UDP CRITICAL OSERROR: {e}\n")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Simplified UDP: CRITICAL Unhandled error in simplified main execution block: {e}", exc_info=True)
        sys.stderr.write(f"Simplified UDP CRITICAL ERROR: {e}\n")
        sys.exit(1)

    # Этот print не должен быть достигнут, если сервер работает в asyncio.Event().wait()
    # logging.info("[GAME_SERVER_MAIN_DEBUG] Reached end of if __name__ == '__main__'.")
```
