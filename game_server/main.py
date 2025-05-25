# game_server/main.py
import asyncio
import logging # Добавляем импорт
from .udp_handler import GameUDPProtocol
from .session_manager import SessionManager
from .tank_pool import TankPool
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE
from prometheus_client import start_http_server
import threading

# Настройка базового логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

    _ = SessionManager()
    _ = TankPool(pool_size=50) 

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(),
        local_addr=(host, port))

    logger.info(f"Игровой UDP сервер запущен и слушает на {transport.get_extra_info('sockname')}")

    try:
        await asyncio.Event().wait() 
    finally:
        logger.info("Остановка игрового UDP сервера...")
        transport.close()

if __name__ == '__main__':
    start_metrics_server()
    try:
        asyncio.run(start_game_server())
    except KeyboardInterrupt:
        logger.info("Сервер остановлен вручную.")
    except Exception as e: # Добавим логирование общих ошибок при старте
        logger.critical(f"Критическая ошибка при запуске/работе игрового сервера: {e}", exc_info=True)
