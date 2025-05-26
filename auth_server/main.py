# auth_server/main.py
import asyncio
import logging # Добавляем импорт
from .tcp_handler import handle_auth_client
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импорт метрик
from prometheus_client import start_http_server
import threading

# Настройка базового логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Создаем логгер для этого модуля

def start_metrics_server():
    # ... (код без изменений)
    start_http_server(8000) 
    logger.info("Prometheus metrics server started on port 8000 for Auth Server.")


async def main():
    host = '0.0.0.0'
    port = 8888
    
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()

    server = await asyncio.start_server(
        handle_auth_client, host, port)

    addr = server.sockets[0].getsockname()
    logger.info(f'Сервер аутентификации запущен на {addr}')

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
