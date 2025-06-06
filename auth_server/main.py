# auth_server/main.py
# Главный модуль сервера аутентификации.
# Отвечает за запуск TCP-сервера для обработки запросов аутентификации
# и сервера метрик Prometheus.
import asyncio
import logging # Добавляем импорт
import sys # Добавлено для вывода в stderr
import os # Добавлено для os.getenv
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
    metrics_port = 8000 # Порт Prometheus для сервера аутентификации
    try:
        print(f"[AuthServerMetrics] Попытка запуска сервера Prometheus на порту {metrics_port}.", flush=True, file=sys.stderr)
        start_http_server(metrics_port) 
        logger.info(f"Prometheus metrics server for Authentication Server started on port {metrics_port}.")
        print(f"[AuthServerMetrics] Сервер Prometheus запущен на порту {metrics_port}.", flush=True, file=sys.stderr)
    except OSError as e:
        logger.error(f"OSError starting Prometheus metrics server on port {metrics_port}: {e}", exc_info=True)
        print(f"[AuthServerMetrics] CRITICAL: OSError при запуске сервера Prometheus на порту {metrics_port}: {e}", flush=True, file=sys.stderr)
        # Эта ошибка в демон-потоке может не остановить основное приложение напрямую, если не обработана выходом.
    except Exception as e_metrics:
        logger.error(f"Failed to start Prometheus metrics server on port {metrics_port}: {e_metrics}", exc_info=True)
        print(f"[AuthServerMetrics] ERROR: Не удалось запустить сервер Prometheus на порту {metrics_port}: {e_metrics}", flush=True, file=sys.stderr)

async def main():
    """
    Основная асинхронная функция для запуска сервера аутентификации.
    Инициализирует и запускает TCP-сервер для приема клиентских подключений
    и сервер метрик.
    """
    DEFAULT_AUTH_HOST = '0.0.0.0'
    DEFAULT_AUTH_PORT = 8888
    AUTH_HOST_ENV_VAR = 'AUTH_SERVER_HOST'
    AUTH_PORT_ENV_VAR = 'AUTH_SERVER_PORT'

    host = os.environ.get(AUTH_HOST_ENV_VAR, DEFAULT_AUTH_HOST)

    try:
        port_str = os.environ.get(AUTH_PORT_ENV_VAR)
        if port_str:
            port = int(port_str)
            logger.info(f"Используется порт из переменной окружения {AUTH_PORT_ENV_VAR}: {port}")
        else:
            port = DEFAULT_AUTH_PORT
            logger.info(f"Переменная окружения {AUTH_PORT_ENV_VAR} не установлена, используется порт по умолчанию: {port}")
    except ValueError:
        port_str_val = os.environ.get(AUTH_PORT_ENV_VAR) # Повторно получаем для логирования
        port = DEFAULT_AUTH_PORT
        logger.warning(f"Не удалось преобразовать значение переменной окружения {AUTH_PORT_ENV_VAR} ('{port_str_val}') в число. Используется порт по умолчанию: {port}")
    
    logger.info(f"Сервер аутентификации будет запущен на {host}:{port}.")

    # Запуск сервера метрик в отдельном потоке.
    # daemon=True означает, что поток завершится при завершении основного процесса.
    # metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    # metrics_thread.name = "AuthMetricsServerThread" # Даем имя потоку
    # metrics_thread.start()
    logger.info("Prometheus metrics server startup is currently COMMENTED OUT for debugging.") # Запуск сервера метрик Prometheus в данный момент ЗАКОММЕНТИРОВАН для отладки.

    server = None # Инициализируем сервер как None
    try:
        # Запуск TCP-сервера с использованием asyncio.
        # handle_auth_client будет вызываться для каждого нового клиентского подключения.
        server = await asyncio.start_server(
            handle_auth_client, host, port)

        addr = server.sockets[0].getsockname() # Получаем адрес и порт, на котором запущен сервер
        logger.info(f'Authentication server started on {addr}')
        print(f"[AuthServerMainLoop] Сервер аутентификации слушает на {addr}", flush=True, file=sys.stderr)
    except OSError as e:
        logger.critical(f"Could not start Authentication server on {host}:{port}: {e}", exc_info=True)
        print(f"[AuthServerMainLoop] CRITICAL: OSError при привязке основного сервера аутентификации к {host}:{port}: {e}", flush=True, file=sys.stderr)
        # Рассмотрите sys.exit(1) или повторный вызов исключения, чтобы процесс завершился, если сервер не может запуститься
        return # Выход, если сервер не может быть привязан
    except Exception as e_main_server:
        logger.critical(f"Unexpected error starting main Authentication server: {e_main_server}", exc_info=True)
        print(f"[AuthServerMainLoop] CRITICAL: Неожиданная ошибка при запуске основного сервера аутентификации: {e_main_server}", flush=True, file=sys.stderr)
        return


    # Бесконечный цикл для обслуживания подключений.
    if server:
        try:
            # async with server: # Временно удаляем async with для упрощения
            logger.info("Auth Server: About to call server.start_serving().")
            print("[AuthServerMainLoop] Сейчас будет вызван server.start_serving().", flush=True, file=sys.stderr)
            await server.start_serving() # Явно начинаем обслуживание
            logger.info("Auth Server: server.start_serving() completed. Entering wait loop.")
            print("[AuthServerMainLoop] server.start_serving() завершен. Вход в цикл ожидания.", flush=True, file=sys.stderr)
            await asyncio.Event().wait() # Поддерживать активность неопределенно долго
            # logger.info("Auth Server: server.serve_forever() exited normally (SHOULD NOT HAPPEN IN NORMAL RUN).")
            # print("[AuthServerMainLoop] server.serve_forever() завершился нормально (НЕ ДОЛЖНО ПРОИСХОДИТЬ В ОБЫЧНОМ РЕЖИМЕ).", flush=True, file=sys.stderr)
        except KeyboardInterrupt: # Разрешить чистое завершение через Ctrl+C при прямом запуске
            logger.info("Authentication server shutting down (KeyboardInterrupt).")
            print("[AuthServerMainLoop] Получено KeyboardInterrupt.", flush=True, file=sys.stderr)
        except Exception as e_serve:
            logger.error(f"Auth Server: Exception during server operation: {e_serve}", exc_info=True)
            print(f"[AuthServerMainLoop] Исключение во время работы сервера: {e_serve}", flush=True, file=sys.stderr)
        finally:
            logger.info("Authentication server main loop ended (inside finally). Cleaning up server.")
            print("[AuthServerMainLoop] Вошли в блок finally основного цикла операций.", flush=True, file=sys.stderr)
            if server and server.is_serving():
                server.close()
                await server.wait_closed()
            logger.info("Authentication server fully stopped.")
    else:
        logger.error("Main server object was not created or failed to bind. Auth server cannot start.")
        print("[AuthServerMainLoop] Главный объект сервера не был создан или не удалось выполнить привязку. Сервер аутентификации не может запуститься.", flush=True, file=sys.stderr)


if __name__ == '__main__':
    # Точка входа в приложение.
    # Запускает основную асинхронную функцию main.
    print("[AuthServerMainScript] Инициализация сервера аутентификации.", flush=True, file=sys.stderr)
    # BasicConfig должен быть в самом начале, если возможно, или используйте специальную функцию конфигурации логирования.
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Auth Server application stopped by KeyboardInterrupt (at asyncio.run level).")
        print("[AuthServerMainScript] Приложение сервера аутентификации остановлено KeyboardInterrupt.", flush=True, file=sys.stderr)
    except Exception as e_run: # Перехват других потенциальных ошибок из asyncio.run или main(), если она возвращается раньше из-за ошибки
        logger.critical(f"Auth Server application CRASHED: {e_run}", exc_info=True)
        print(f"[AuthServerMainScript] CRITICAL error running Auth Server application: {e_run}", flush=True, file=sys.stderr)
