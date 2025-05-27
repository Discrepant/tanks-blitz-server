# game_server/main.py
import asyncio
import logging # Добавляем импорт
import time # Added for the main loop in finally example, though not strictly needed for this change
import functools # Added import
import os # Added import
from .udp_handler import GameUDPProtocol
from .tcp_handler import handle_game_client # Added import
from .game_logic import GameRoom # Added import
from .auth_client import AuthClient # Added import
from .session_manager import SessionManager
from .tank_pool import TankPool
from .command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer # Added MatchmakingEventConsumer
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE
from prometheus_client import start_http_server
import threading

# Настройка базового логирования
# Moved logging configuration to if __name__ == '__main__' to ensure it's configured before other loggers might be initialized
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Создаем логгер для этого модуля

def update_metrics():
    # ... (код без изменений)
    sm = SessionManager()
    tp = TankPool()
    ACTIVE_SESSIONS.set(len(sm.sessions))
    TANKS_IN_USE.set(len(tp.in_use_tanks))


def metrics_updater_loop():
    # ... (код без изменений)
    # Этот цикл выполняется в отдельном потоке, для него можно настроить свой логгер, если нужно
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def updater():
        while True:
            update_metrics()
            await asyncio.sleep(5)
    try: # Добавим try/finally для закрытия цикла
        loop.run_until_complete(updater())
    finally:
        loop.close()


def start_metrics_server():
    # ... (код без изменений)
    start_http_server(8001)
    logger.info("Prometheus metrics server started on port 8001 for Game Server.")
    metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
    metrics_loop_thread.start()


async def start_game_server():
    host = '0.0.0.0'
    port = 9999

    logger.info(f"Запуск игрового UDP сервера на {host}:{port}...")
    loop = asyncio.get_running_loop()

    # SessionManager and TankPool will be initialized in main or passed if needed
    # For now, assuming they are singletons and will be initialized in __main__
    # or their existing instantiation in update_metrics and here is sufficient.
    # For PlayerCommandConsumer, we need specific instances.

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(), # GameUDPProtocol might need access to session_manager and tank_pool
        local_addr=(host, port))

    logger.info(f"Игровой UDP сервер запущен и слушает на {transport.get_extra_info('sockname')}")

    # Start TCP server
    game_tcp_host = os.getenv('GAME_SERVER_TCP_HOST', '0.0.0.0')
    game_tcp_port = int(os.getenv('GAME_SERVER_TCP_PORT', 8889))
    auth_server_host = os.getenv('AUTH_SERVER_HOST', 'localhost')
    auth_server_port = int(os.getenv('AUTH_SERVER_PORT', 8888))

    auth_client = AuthClient(auth_server_host=auth_server_host, auth_server_port=auth_server_port)
    game_room = GameRoom(auth_client=auth_client)

    tcp_server_handler = functools.partial(handle_game_client, game_room=game_room)
    tcp_server = await loop.create_server(
        tcp_server_handler,
        game_tcp_host,
        game_tcp_port
    )
    logger.info(f"Игровой TCP сервер запущен и слушает на {game_tcp_host}:{game_tcp_port}")
    # Example of logging actual bound address: logger.info(f"TCP Server actually listening on {tcp_server.sockets[0].getsockname()}")


    try:
        await asyncio.Event().wait() 
    finally:
        logger.info("Остановка игровых серверов...")
        # Stop TCP server
        if 'tcp_server' in locals() and tcp_server:
            tcp_server.close()
            await tcp_server.wait_closed()
            logger.info("Игровой TCP сервер остановлен.")
        # Stop UDP server
        if 'transport' in locals() and transport:
            transport.close()
            logger.info("Игровой UDP сервер остановлен.")


if __name__ == '__main__':
    # Configure logging here so it's set up early
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Starting game server application...")

    # Initialize shared instances of SessionManager and TankPool
    # These are likely designed as singletons or manage global state.
    # If they are not, this approach needs refinement to ensure the same instances
    # are used by GameUDPProtocol, PlayerCommandConsumer, and metrics.
    session_manager = SessionManager()
    tank_pool = TankPool(pool_size=50) # Initialize with a pool size

    # Start Prometheus metrics server
    start_metrics_server() # This function already uses new instances of SM and TP, may need to be refactored if shared instances are strict.

    # Initialize and start RabbitMQ Player Command Consumer
    logger.info("Initializing PlayerCommandConsumer...")
    player_command_consumer = PlayerCommandConsumer(session_manager, tank_pool)
    
    consumer_thread = threading.Thread(target=player_command_consumer.start_consuming, daemon=True)
    consumer_thread.setName("PlayerCommandConsumerThread") # Good for debugging
    consumer_thread.start()
    logger.info("PlayerCommandConsumer started in a separate thread.")

    # Initialize and start RabbitMQ Matchmaking Event Consumer
    logger.info("Initializing MatchmakingEventConsumer...")
    matchmaking_event_consumer = MatchmakingEventConsumer(session_manager) # Uses the same session_manager
    
    matchmaking_consumer_thread = threading.Thread(
        target=matchmaking_event_consumer.start_consuming, 
        daemon=True, 
        name="MatchmakingEventConsumerThread"
    )
    matchmaking_consumer_thread.start()
    logger.info("MatchmakingEventConsumer started in a separate thread.")

    # Start the main game server
    try:
        logger.info("Starting asynchronous game server components...")
        # Pass session_manager and tank_pool to start_game_server if it needs them explicitly
        # For now, assuming GameUDPProtocol gets them via singleton pattern from SessionManager/TankPool
        asyncio.run(start_game_server()) 
    except KeyboardInterrupt:
        logger.info("Server shutdown initiated by KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Critical error during server runtime: {e}", exc_info=True)
    finally:
        logger.info("Attempting to stop consumers...")
        if 'player_command_consumer' in locals() and player_command_consumer:
            player_command_consumer.stop_consuming()
        if 'consumer_thread' in locals() and consumer_thread.is_alive():
            logger.info("Waiting for PlayerCommandConsumerThread to join...")
            consumer_thread.join(timeout=5) # Wait for thread to finish
            if consumer_thread.is_alive():
                logger.warning("PlayerCommandConsumerThread did not terminate cleanly.")
            else:
                logger.info("PlayerCommandConsumerThread joined successfully.")

        if 'matchmaking_event_consumer' in locals() and matchmaking_event_consumer:
            matchmaking_event_consumer.stop_consuming()
        if 'matchmaking_consumer_thread' in locals() and matchmaking_consumer_thread.is_alive():
            logger.info("Waiting for MatchmakingEventConsumerThread to join...")
            matchmaking_consumer_thread.join(timeout=5) # Wait for thread to finish
            if matchmaking_consumer_thread.is_alive():
                logger.warning("MatchmakingEventConsumerThread did not terminate cleanly.")
            else:
                logger.info("MatchmakingEventConsumerThread joined successfully.")
        
        logger.info("Game server application shut down complete.")
