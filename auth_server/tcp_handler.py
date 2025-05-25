# auth_server/tcp_handler.py
import asyncio
import logging # Добавляем импорт
from .user_service import authenticate_user
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def handle_auth_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info('peername')
    logger.info(f"Новое подключение от {addr}")
    ACTIVE_CONNECTIONS_AUTH.inc()

    try:
        # Логируем сырые данные перед декодированием
        data = await reader.read(1024) # Читаем до 1024 байт
        if not data:
            logger.warning(f"Нет данных от клиента {addr}. Закрытие соединения.")
            return # Нет смысла продолжать, если данных нет

        logger.debug(f"Получены сырые данные от {addr}: {data!r}") # Используем !r для отображения байтов

        message = data.decode().strip()
        logger.debug(f"Декодированное сообщение от {addr}: '{message}'")

        parts = message.split()
        logger.debug(f"Сообщение разделено на части: {parts}")

        if len(parts) == 3 and parts[0].upper() == 'LOGIN':
            command, username, password = parts[0].upper(), parts[1], parts[2]
            logger.info(f"Получена команда '{command}' от {addr} для пользователя '{username}'")
            
            is_authenticated, response_message = await authenticate_user(username, password)
            
            if is_authenticated:
                SUCCESSFUL_AUTHS.inc()
                response_str = f"AUTH_SUCCESS {response_message}\n"
                logger.info(f"Пользователь '{username}' успешно аутентифицирован. Ответ: {response_str.strip()}")
            else:
                FAILED_AUTHS.inc()
                response_str = f"AUTH_FAILURE {response_message}\n"
                logger.warning(f"Неудачная попытка аутентификации для пользователя '{username}'. Причина: {response_message}. Ответ: {response_str.strip()}")
            
            writer.write(response_str.encode())
            logger.debug(f"Отправлен ответ клиенту {addr}: {response_str.strip()}")
        else:
            response_str = "INVALID_COMMAND Формат: LOGIN username password\n"
            logger.warning(f"Получена неверная команда от {addr}: '{message}'. Ответ: {response_str.strip()}")
            writer.write(response_str.encode())
            logger.debug(f"Отправлен ответ клиенту {addr}: {response_str.strip()}")

        await writer.drain()
        logger.debug(f"Данные для {addr} сброшены в поток.")

    except ConnectionResetError:
        logger.warning(f"Соединение сброшено клиентом {addr}.")
        # FAILED_AUTHS.inc() # Можно не считать это неудачной аутентификацией, а проблемой сети
    except asyncio.IncompleteReadError:
        logger.warning(f"Неполное чтение от клиента {addr}. Соединение могло быть закрыто преждевременно.")
    except Exception as e:
        # Логируем исключение с полной трассировкой
        logger.exception(f"Ошибка при обработке клиента {addr}:")
        # FAILED_AUTHS.inc() # Считаем это неудачей, если ошибка произошла до успешной аутентификации
        
        # Попытка отправить сообщение об ошибке, если writer еще доступен
        if not writer.is_closing():
            try:
                error_response = f"ERROR_INTERNAL_SERVER_ERROR Произошла внутренняя ошибка сервера.\n"
                writer.write(error_response.encode())
                await writer.drain()
                logger.debug(f"Отправлено сообщение об ошибке клиенту {addr}: {error_response.strip()}")
            except Exception as ex_send:
                logger.error(f"Не удалось отправить сообщение об ошибке клиенту {addr}: {ex_send}")
    finally:
        logger.info(f"Закрытие соединения с {addr}")
        ACTIVE_CONNECTIONS_AUTH.dec()
        if not writer.is_closing():
            writer.close()
            try:
                await writer.wait_closed() # Ждем, пока соединение действительно закроется
            except Exception as e_close:
                logger.error(f"Ошибка при ожидании закрытия writer для {addr}: {e_close}")
        logger.debug(f"Соединение с {addr} полностью закрыто.")
