# game_server/main.py
import asyncio
from .udp_handler import GameUDPProtocol
from .session_manager import SessionManager
from .tank_pool import TankPool
from prometheus_client import start_http_server, Gauge, Counter
import threading

# Определяем метрики Prometheus
ACTIVE_SESSIONS = Gauge('game_server_active_sessions', 'Number of active game sessions')
TANKS_IN_USE = Gauge('game_server_tanks_in_use', 'Number of tanks currently in use from the pool')
TOTAL_DATAGRAMS_RECEIVED = Counter('game_server_datagrams_received_total', 'Total number of UDP datagrams received')
TOTAL_PLAYERS_JOINED = Counter('game_server_players_joined_total', 'Total number of players joined')


def update_metrics():
    # Обновляем метрики, которые зависят от состояния синглтонов
    # Это можно делать периодически или по событиям
    # В данном случае, SessionManager и TankPool сами по себе не являются источниками событий для метрик,
    # поэтому мы будем обновлять их значения здесь, в цикле.
    # Для Gauge метрик, которые отражают текущее состояние, это нормально.
    # Для более точного подсчета лучше интегрировать inc/dec в методы SessionManager/TankPool.
    sm = SessionManager()
    tp = TankPool()
    
    ACTIVE_SESSIONS.set(len(sm.sessions))
    TANKS_IN_USE.set(len(tp.in_use_tanks))
    # TOTAL_DATAGRAMS_RECEIVED и TOTAL_PLAYERS_JOINED будут инкрементироваться в udp_handler

def metrics_updater_loop():
    # Создаем новый цикл событий для этого потока, т.к. основной цикл asyncio работает в главном потоке
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def updater():
        while True:
            update_metrics()
            await asyncio.sleep(5) # Обновлять каждые 5 секунд
    try:
        loop.run_until_complete(updater())
    finally:
        loop.close()


def start_metrics_server():
    start_http_server(8001) # Отдельный порт для Prometheus
    print("Prometheus metrics server started on port 8001 for Game Server.")
    # Запуск цикла обновления метрик в отдельном потоке
    metrics_loop_thread = threading.Thread(target=metrics_updater_loop, daemon=True)
    metrics_loop_thread.start()


async def start_game_server():
    host = '0.0.0.0'
    port = 9999

    print(f"Запуск игрового UDP сервера на {host}:{port}...")
    
    # Запуск HTTP сервера для метрик уже сделан в __main__

    loop = asyncio.get_running_loop()

    _ = SessionManager() # Инициализация
    _ = TankPool(pool_size=50) 

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GameUDPProtocol(), # GameUDPProtocol должен будет инкрементировать счетчики
        local_addr=(host, port))

    print(f"Игровой UDP сервер запущен и слушает на {transport.get_extra_info('sockname')}")

    try:
        # Бесконечное ожидание, чтобы сервер продолжал работать
        # asyncio.Event().wait() блокирует, поэтому используем другой подход для асинхронного ожидания
        while True:
            await asyncio.sleep(3600) # Просыпаться каждый час или просто ждать
    except asyncio.CancelledError:
        print("Основная задача сервера была отменена.")
    finally:
        print("Остановка игрового UDP сервера...")
        transport.close()

if __name__ == '__main__':
    start_metrics_server() # Запускаем сервер метрик перед запуском основного цикла asyncio
    try:
        asyncio.run(start_game_server())
    except KeyboardInterrupt:
        print("Сервер остановлен вручную.")
    except Exception as e:
        print(f"Критическая ошибка в основном цикле сервера: {e}")
