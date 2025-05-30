# game_server/main.py
# Главный модуль игрового сервера.
# Отвечает за инициализацию и запуск всех компонентов игрового сервера:
# - UDP-сервер для основного игрового взаимодействия.
# - TCP-сервер для управляющих команд и чата.
# - Клиент для сервера аутентификации.
# - Менеджер игровых сессий и пул объектов танков.
# - Потребители сообщений из RabbitMQ для команд игроков и событий матчмейкинга.
# - Сервер метрик Prometheus.

# --- BEGIN DEBUG PRINTS ---
import sys
import os
print(f"[GAME_SERVER_MAIN_DEBUG] STARTING game_server/main.py", flush=True)
print(f"[GAME_SERVER_MAIN_DEBUG] Current sys.path: {sys.path}", flush=True)
print(f"[GAME_SERVER_MAIN_DEBUG] Current os.getcwd(): {os.getcwd()}", flush=True)
print(f"[GAME_SERVER_MAIN_DEBUG] Environ USE_MOCKS: {os.environ.get('USE_MOCKS')}", flush=True)
print(f"[GAME_SERVER_MAIN_DEBUG] Environ PYTHONPATH: {os.environ.get('PYTHONPATH')}", flush=True)

try:
    import core.message_broker_clients
    print(f"[GAME_SERVER_MAIN_DEBUG] core.message_broker_clients path: {core.message_broker_clients.__file__}", flush=True)
except ImportError as e_core_mbc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import core.message_broker_clients: {e_core_mbc}", flush=True)

try:
    import game_server.command_consumer
    print(f"[GAME_SERVER_MAIN_DEBUG] game_server.command_consumer path: {game_server.command_consumer.__file__}", flush=True)
except ImportError as e_gs_cc:
    print(f"[GAME_SERVER_MAIN_DEBUG] FAILED to import game_server.command_consumer: {e_gs_cc}", flush=True)
# --- END DEBUG PRINTS ---

import logging # Добавляем импорт для логирования
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
import os # Добавлен импорт для работы с переменными окружения
from .udp_handler import GameUDPProtocol # Обработчик UDP-пакетов
from .tcp_handler import handle_game_client # Обработчик TCP-соединений
from .game_logic import GameRoom # Логика игровой комнаты
from .auth_client import AuthClient # Клиент для сервера аутентификации
from .session_manager import SessionManager # Менеджер игровых сессий
from .tank_pool import TankPool # Пул объектов танков
from .command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer # Потребители сообщений из RabbitMQ
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE # Метрики Prometheus
from prometheus_client import start_http_server # Функция для запуска сервера метрик
import threading # Для запуска компонентов в отдельных потоках

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')
# Настройка базового логирования.
# Перенесена в блок if __name__ == '__main__', чтобы гарантировать настройку
# до инициализации других логгеров.
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Создаем логгер для текущего модуля

# Define a file path for integration test logging
INTEGRATION_TEST_LOG_FILE = "/tmp/game_server_integration_test.log"

# Function to set up file logging
def setup_file_logging():
    try:
        # Clear previous log file
        if os.path.exists(INTEGRATION_TEST_LOG_FILE):
            os.remove(INTEGRATION_TEST_LOG_FILE)
        
        file_handler = logging.FileHandler(INTEGRATION_TEST_LOG_FILE)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler) # Add to root logger to capture all logs
        logging.getLogger().setLevel(logging.DEBUG) # Ensure root logger level is low enough
        logger.info(f"File logging set up to {INTEGRATION_TEST_LOG_FILE}")
        print(f"[GameServerMain] File logging configured to {INTEGRATION_TEST_LOG_FILE}", flush=True, file=sys.stderr)
    except Exception as e:
        print(f"[GameServerMain] ERROR setting up file logging: {e}", flush=True, file=sys.stderr)


def update_metrics():
    """
    Обновляет значения метрик Prometheus на основе текущего состояния
    SessionManager и TankPool.
    """
    # ... (код без изменений) - Этот комментарий указывает, что код ниже не требует перевода, так как он на русском или является кодом.
    sm = SessionManager() # Получаем экземпляр SessionManager (предполагается Singleton)
    tp = TankPool()       # Получаем экземпляр TankPool (предполагается Singleton)
    ACTIVE_SESSIONS.set(len(sm.sessions)) # Устанавливаем метрику активных сессий
    TANKS_IN_USE.set(len(tp.in_use_tanks)) # Устанавливаем метрику используемых танков


def metrics_updater_loop():
    """
    Асинхронный цикл для периодического обновления метрик Prometheus.
    Запускается в отдельном потоке.
    """
    # ... (код без изменений)
    # Этот цикл выполняется в отдельном потоке, для него можно настроить свой логгер, если нужно.
    loop = asyncio.new_event_loop() # Создаем новый цикл событий для этого потока
    asyncio.set_event_loop(loop)    # Устанавливаем его как текущий для потока
    async def updater():
        """Внутренняя асинхронная функция, которая бесконечно обновляет метрики."""
        while True:
            update_metrics()
            await asyncio.sleep(5) # Пауза 5 секунд между обновлениями
    try: # Добавляем try/finally для корректного закрытия цикла событий
        loop.run_until_complete(updater())
    finally:
        loop.close() # Закрываем цикл событий при завершении


def start_metrics_server():
    """
    Запускает HTTP-сервер для метрик Prometheus и поток для их обновления.
    """
    # ... (код без изменений)
    start_http_server(8001) # Запускаем HTTP-сервер Prometheus на порту 8001
    logger.info("Prometheus metrics server for Game Server started on port 8001.")
    # Запускаем цикл обновления метрик в отдельном daemon-потоке
    metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
    metrics_loop_thread.setName("MetricsUpdaterThread") # Даем имя потоку для удобства отладки
    metrics_loop_thread.start()


async def start_game_server():
    """
    Основная асинхронная функция для запуска UDP и TCP серверов игры.
    Настраивает обработчики, игровую комнату и клиент аутентификации.
    """
    host = '0.0.0.0' # Слушаем на всех доступных интерфейсах
    port = 9999      # Порт для UDP-сервера

    logger.info(f"Starting game UDP server on {host}:{port}...")
    loop = asyncio.get_running_loop() # Получаем текущий цикл событий

    # SessionManager и TankPool будут инициализированы в main или переданы при необходимости.
    # Пока предполагается, что они являются синглтонами и будут инициализированы в __main__
    # или их существующие экземпляры в update_metrics и здесь достаточны.
    # Для PlayerCommandConsumer нам нужны конкретные экземпляры.
    # Примечание переводчика: комментарий выше актуален для понимания архитектуры.

    # Создаем конечную точку UDP-сервера
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(), # GameUDPProtocol может потребоваться доступ к session_manager и tank_pool
        local_addr=(host, port)
    )

    logger.info(f"Game UDP server started and listening on {transport.get_extra_info('sockname')}")

    # Запуск TCP-сервера
    game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
    game_tcp_port = int(os.getenv('GAME_SERVER_TCP_PORT', 8889))
    auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
    auth_server_port = int(os.getenv('AUTH_SERVER_PORT', 8888))
    logger.info(f"AuthClient will connect to {auth_server_host}:{auth_server_port}")
    print(f"[GameServerMain_start_game_server] AuthClient target: {auth_server_host}:{auth_server_port}", flush=True, file=sys.stderr)

    try:
        auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
        logger.info("AuthClient initialized successfully.")
        print("[GameServerMain_start_game_server] AuthClient initialized.", flush=True, file=sys.stderr)
        
        game_room = GameRoom(auth_client=auth_client)
        logger.info("GameRoom initialized successfully.")
        print("[GameServerMain_start_game_server] GameRoom initialized.", flush=True, file=sys.stderr)
        
        tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
        logger.info("TCP server handler (partial) created.")
        print("[GameServerMain_start_game_server] TCP handler partial created.", flush=True, file=sys.stderr)
        
        # Ensure using asyncio.start_server as per previous fix
        tcp_server = await asyncio.start_server( 
            tcp_server_handler,
            game_tcp_host,
            game_tcp_port
        )
        logger.info(f"Game TCP server created using asyncio.start_server and listening on {game_tcp_host}:{game_tcp_port}")
        print(f"[GameServerMain_start_game_server] Game TCP server created using asyncio.start_server, listening on {game_tcp_host}:{game_tcp_port}.", flush=True, file=sys.stderr)

    except Exception as e_setup:
        logger.critical(f"CRITICAL ERROR during server setup: {e_setup}", exc_info=True)
        print(f"[GameServerMain_start_game_server] CRITICAL ERROR during server setup: {e_setup}", flush=True, file=sys.stderr)
        return # Stop if setup fails

    try:
        await asyncio.Event().wait() 
    finally:
        logger.info("Stopping game servers...")
        print("[GameServerMain_start_game_server] Stopping game servers in finally block.", flush=True, file=sys.stderr)
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
    # Настраиваем логирование здесь, чтобы оно было установлено как можно раньше.
    setup_file_logging() # Setup file logging
    logger.info("Starting game server application...")
    print("[GameServerMain] Starting game server application.", flush=True, file=sys.stderr)

    # Инициализация общих экземпляров SessionManager и TankPool.
    # Вероятно, они спроектированы как синглтоны или управляют глобальным состоянием.
    # Если нет, этот подход требует доработки, чтобы гарантировать использование
    # одних и тех же экземпляров в GameUDPProtocol, PlayerCommandConsumer и метриках.
    # Примечание переводчика: комментарий выше актуален для понимания архитектуры.
    session_manager = SessionManager()
    tank_pool = TankPool(pool_size=50) # Инициализируем с размером пула

    # Запуск сервера метрик Prometheus
    # Эта функция уже использует новые экземпляры SM и TP, может потребоваться рефакторинг,
    # если строго необходимы общие экземпляры.
    # Примечание переводчика: комментарий выше актуален для понимания архитектуры.
    start_metrics_server() 

    # Инициализация и запуск потребителя команд игроков из RabbitMQ
    logger.info("Initializing PlayerCommandConsumer...")
    player_command_consumer = PlayerCommandConsumer(session_manager, tank_pool)
    
    # Запускаем потребителя в отдельном daemon-потоке
    consumer_thread = threading.Thread(target=player_command_consumer.start_consuming, daemon=True)
    consumer_thread.setName("PlayerCommandConsumerThread") # Имя потока полезно для отладки
    consumer_thread.start()
    logger.info("PlayerCommandConsumer started in a separate thread.")

    # Инициализация и запуск потребителя событий матчмейкинга из RabbitMQ
    logger.info("Initializing MatchmakingEventConsumer...")
    matchmaking_event_consumer = MatchmakingEventConsumer(session_manager) # Использует тот же session_manager
    
    # Запускаем потребителя событий матчмейкинга в отдельном daemon-потоке
    matchmaking_consumer_thread = threading.Thread(
        target=matchmaking_event_consumer.start_consuming, 
        daemon=True, 
        name="MatchmakingEventConsumerThread" # Имя потока
    )
    matchmaking_consumer_thread.start()
    logger.info("MatchmakingEventConsumer started in a separate thread.")

    # Запуск основного игрового сервера
    try:
        logger.info("Starting asynchronous components of the game server...")
        # Передаем session_manager и tank_pool в start_game_server, если это необходимо явно.
        # Пока предполагается, что GameUDPProtocol получает их через паттерн Singleton из SessionManager/TankPool.
        # Примечание переводчика: комментарий выше актуален для понимания архитектуры.
        asyncio.run(start_game_server()) 
    except KeyboardInterrupt:
        logger.info("Server shutdown initiated via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Critical error during server execution: {e}", exc_info=True)
    finally:
        logger.info("Attempting to stop consumers...")
        # Корректная остановка потребителя команд игроков
        if 'player_command_consumer' in locals() and player_command_consumer:
            player_command_consumer.stop_consuming()
        if 'consumer_thread' in locals() and consumer_thread.is_alive():
            logger.info("Waiting for PlayerCommandConsumerThread to complete...")
            consumer_thread.join(timeout=5) # Ожидаем завершения потока с таймаутом
            if consumer_thread.is_alive():
                logger.warning("PlayerCommandConsumerThread did not complete correctly.")
            else:
                logger.info("PlayerCommandConsumerThread completed successfully.")

        # Корректная остановка потребителя событий матчмейкинга
        if 'matchmaking_event_consumer' in locals() and matchmaking_event_consumer:
            matchmaking_event_consumer.stop_consuming()
        if 'matchmaking_consumer_thread' in locals() and matchmaking_consumer_thread.is_alive():
            logger.info("Waiting for MatchmakingEventConsumerThread to complete...")
            matchmaking_consumer_thread.join(timeout=5) # Ожидаем завершения потока с таймаутом
            if matchmaking_consumer_thread.is_alive():
                logger.warning("MatchmakingEventConsumerThread did not complete correctly.")
            else:
                logger.info("MatchmakingEventConsumerThread completed successfully.")
        
        logger.info("Game server application completely stopped.")
