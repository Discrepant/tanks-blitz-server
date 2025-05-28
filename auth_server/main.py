# auth_server/main.py
# Главный модуль сервера аутентификации.
# Отвечает за запуск TCP-сервера для обработки запросов аутентификации
# и сервера метрик Prometheus.
import asyncio
import logging # Добавляем импорт
from .tcp_handler import handle_auth_client # Импортируем обработчик клиентских подключений
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импорт метрик Prometheus
from prometheus_client import start_http_server # Функция для запуска HTTP-сервера метрик
import threading # Используется для запуска сервера метрик в отдельном потоке

# Настройка базового логирования для всего приложения.
# Уровень логирования DEBUG, формат включает время, имя логгера, уровень и сообщение.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__) # Создаем логгер для текущего модуля

def start_metrics_server():
    """
    Запускает HTTP-сервер для сбора метрик Prometheus.
    Сервер запускается на порту 8000.
    """
    # ... (код без изменений) # Эта строка комментария кажется излишней или устаревшей. Удалим ее.
    start_http_server(8000) 
    logger.info("Сервер метрик Prometheus для Сервера Аутентификации запущен на порту 8000.")


async def main():
    """
    Основная асинхронная функция для запуска сервера аутентификации.
    Инициализирует и запускает TCP-сервер для приема клиентских подключений
    и сервер метрик.
    """
    host = '0.0.0.0'  # Сервер будет слушать на всех доступных сетевых интерфейсах
    port = 8888       # Порт для TCP-сервера аутентификации
    
    # Запуск сервера метрик в отдельном потоке.
    # daemon=True означает, что поток завершится при завершении основного процесса.
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()

    # Запуск TCP-сервера с использованием asyncio.
    # handle_auth_client будет вызываться для каждого нового клиентского подключения.
    server = await asyncio.start_server(
        handle_auth_client, host, port)

    addr = server.sockets[0].getsockname() # Получаем адрес и порт, на котором запущен сервер
    logger.info(f'Сервер аутентификации запущен на {addr}')

    # Бесконечный цикл для обслуживания подключений.
    # Сервер будет работать до тех пор, пока не будет прерван.
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    # Точка входа в приложение.
    # Запускает основную асинхронную функцию main.
    asyncio.run(main())
