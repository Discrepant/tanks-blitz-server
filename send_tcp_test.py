# send_tcp_test.py
# Этот скрипт используется для отправки тестовых TCP-сообщений на сервер
# и вывода ответов сервера. Полезен для ручной проверки и отладки TCP-сервера.
import socket
import time
import logging # Добавляем логирование

# Настройка базового логирования для скрипта
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def send_tcp_message(host: str, port: int, message: str):
    """
    Отправляет TCP-сообщение на указанный хост и порт и печатает ответ.

    Args:
        host (str): Хост сервера.
        port (int): Порт сервера.
        message (str): Сообщение для отправки. Сообщение должно быть закодировано
                       в UTF-8 перед отправкой. Ожидается, что сообщение будет
                       завершаться символом новой строки для корректной обработки
                       сервером, использующим reader.readuntil(b'\\n').
    """
    try:
        # Создаем сокет с семейством адресов AF_INET (IPv4) и типом SOCK_STREAM (TCP)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port)) # Подключаемся к серверу
            s.sendall(message.encode('utf-8')) # Отправляем закодированное сообщение
            logger.info(f"Отправлено: {message.strip()}") # Логируем отправленное сообщение
            
            # Получаем ответ от сервера (до 1024 байт)
            response_bytes = s.recv(1024) 
            response_str = response_bytes.decode('utf-8').strip() # Декодируем и очищаем ответ
            logger.info(f"Получено: {response_str}") # Логируем полученный ответ
    except ConnectionRefusedError:
        logger.error(f"Ошибка подключения: не удалось подключиться к {host}:{port}. Сервер недоступен.")
    except socket.timeout:
        logger.error(f"Ошибка: таймаут при ожидании ответа от {host}:{port}.")
    except Exception as e:
        logger.error(f"Ошибка при отправке/получении сообщения: {e}")

if __name__ == "__main__":
    # Целевой хост и порт сервера (например, сервер аутентификации)
    server_host = "localhost"
    server_port = 8888 # Порт сервера аутентификации по умолчанию

    # Список тестовых сообщений для отправки.
    # Каждое сообщение должно завершаться '\n' для корректного чтения readuntil() на сервере.
    messages = [
        # Тестовые случаи для сервера аутентификации (Auth Server)
        '{"action": "login", "username": "player1", "password": "password123"}\n',  # Успешный логин
        '{"action": "login", "username": "testuser", "password": "wrongpass"}\n',   # Неверный пароль
        '{"action": "login", "username": "non_existent_user", "password": "mypass"}\n', # Несуществующий пользователь
        '{"action": "register", "username": "newuser", "password": "newpassword"}\n', # Запрос на регистрацию (mock)
        'INVALID_JSON_STRING\n',    # Невалидный JSON
        '{"unknown_action": "do_something"}\n', # Неизвестное действие
        '{"action": "login"}\n', # Неполный запрос (отсутствуют username/password)
        '{}\n', # Пустой JSON
        '\n', # Пустая строка (после strip() станет пустой)
        'LOGIN player1 password123\n', # Старый текстовый формат (сервер должен его отвергнуть, если ожидает JSON)
    ]

    logger.info(f"Запуск теста отправки TCP-сообщений на {server_host}:{server_port}")
    for msg in messages:
        send_tcp_message(server_host, server_port, msg)
        time.sleep(0.5) # Небольшая задержка между сообщениями
    logger.info("Тест отправки TCP-сообщений завершен.")
