# game_server/main.py
import asyncio
from .udp_handler import GameUDPProtocol # Оставляем импорт протокола
from .session_manager import SessionManager
from .tank_pool import TankPool
# Импортируем метрики из нового файла
from .metrics import ACTIVE_SESSIONS, TANKS_IN_USE 
# TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED будут использоваться в udp_handler
from prometheus_client import start_http_server
import threading

# Функция update_metrics остается здесь, так как она зависит от SessionManager и TankPool,
# которые являются частью game_server и могут создавать циклический импорт, если эту функцию перенести в metrics.py
def update_metrics():
    sm = SessionManager()
    tp = TankPool()
    
    ACTIVE_SESSIONS.set(len(sm.sessions))
    TANKS_IN_USE.set(len(tp.in_use_tanks))

def metrics_updater_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def updater():
        while True:
            update_metrics() # Использует импортированные ACTIVE_SESSIONS, TANKS_IN_USE
            await asyncio.sleep(5)
    try:
        loop.run_until_complete(updater())
    finally:
        loop.close()

def start_metrics_server():
    start_http_server(8001)
    print("Prometheus metrics server started on port 8001 for Game Server.")
    metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
    metrics_loop_thread.start()

async def start_game_server():
    host = '0.0.0.0'
    port = 9999

    print(f"Запуск игрового UDP сервера на {host}:{port}...")
    loop = asyncio.get_running_loop()

    _ = SessionManager()
    _ = TankPool(pool_size=50) 

    # GameUDPProtocol будет импортировать нужные ему Counter метрики из game_server.metrics
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(),
        local_addr=(host, port))

    print(f"Игровой UDP сервер запущен и слушает на {transport.get_extra_info('sockname')}")

    try:
        await asyncio.Event().wait() 
    finally:
        print("Остановка игрового UDP сервера...")
        transport.close()

if __name__ == '__main__':
    start_metrics_server()
    try:
        asyncio.run(start_game_server())
    except KeyboardInterrupt:
        print("Сервер остановлен вручную.")
    except Exception as e:
        print(f"Критическая ошибка в основном цикле сервера: {e}")
