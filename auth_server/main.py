# auth_server/main.py
import asyncio
from .tcp_handler import handle_auth_client
from prometheus_client import start_http_server # Gauge, Counter теперь импортируются из metrics.py
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импорт из нового файла
import threading

# Определения метрик Prometheus УДАЛЕНЫ отсюда, так как они теперь в metrics.py

def start_metrics_server():
    start_http_server(8000) # Отдельный порт для Prometheus
    print("Prometheus metrics server started on port 8000 for Auth Server.")

async def main():
    host = '0.0.0.0'
    port = 8888

    # Запуск HTTP сервера для метрик в отдельном потоке
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()

    server = await asyncio.start_server(
        handle_auth_client, host, port)

    addr = server.sockets[0].getsockname()
    print(f'Сервер аутентификации запущен на {addr}')

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
