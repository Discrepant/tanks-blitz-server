# auth_server/tcp_handler.py
# Этот модуль отвечает за обработку TCP-соединений и сообщений от клиентов
# для сервера аутентификации.
import asyncio
import json # Импортируем json для работы с JSON-сообщениями
import logging # Импортируем logging для логирования
from .user_service import authenticate_user # Импортируем функцию аутентификации пользователя
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импортируем метрики Prometheus

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def handle_auth_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Обрабатывает входящее клиентское подключение для аутентификации.

    Читает данные от клиента, ожидает JSON-сообщение с действием (login/register),
    обрабатывает его и отправляет ответ. Обновляет метрики Prometheus.

    Args:
        reader: Объект asyncio.StreamReader для чтения данных от клиента.
        writer: Объект asyncio.StreamWriter для отправки данных клиенту.
    """
    addr = writer.get_extra_info('peername') # Получаем адрес клиента
    logger.info(f"New connection from {addr}, JSON expected.")
    ACTIVE_CONNECTIONS_AUTH.inc() # Увеличиваем счетчик активных соединений
    response_data = {} # Инициализируем переменную для данных ответа

    try:
        # Читаем данные до символа новой строки. Ожидается, что клиент отправит JSON и \n.
        raw_data_bytes = await reader.readuntil(b'\n') 
        
        # Проверка на пустые данные или только символ новой строки перед декодированием
        if not raw_data_bytes.strip(): # MODIFIED - проверяем после strip(), чтобы учесть \n
            logger.warning(f"Empty message or only newline character received from {addr}. Sending error and closing.")
            response_data = {"status": "error", "message": "Empty message or only newline character received"} # Error message updated
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции, finally выполнит очистку
            
        # Декодируем байты в строку UTF-8. Используем строгую проверку.
        raw_data = raw_data_bytes.decode('utf-8') 
        logger.debug(f"TCP Handler: Raw string received from client {addr}: '{raw_data.strip()}'")
        
        # Удаляем пробельные символы с начала и конца строки.
        message_json_str = raw_data.strip()
        
        # Проверка, не является ли строка пустой ПОСЛЕ удаления пробельных символов.
        if not message_json_str: 
            logger.warning(f"Empty message received from {addr} after strip. Sending error and closing.")
            response_data = {"status": "error", "message": "Empty message received"} # This specific error message
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции

        try:
            # message_json_str уже декодирована и очищена от пробелов.
            logger.debug(f"JSON string received from {addr}: '{message_json_str}'")
            message_data = json.loads(message_json_str) # Парсим JSON-строку в Python dict
            logger.debug(f"TCP Handler: Parsed JSON from client {addr}: {message_data}")
            action = message_data.get("action") or message_data.get("command") # Получаем действие из сообщения
            username = message_data.get("username") # Получаем имя пользователя
            password = message_data.get("password") # Получаем пароль

            logger.info(f"Received action '{action}' from {addr} for user '{username}'")

            if action == "login": # Если действие - "login"
                is_authenticated, response_message = await authenticate_user(username, password)
                if is_authenticated:
                    SUCCESSFUL_AUTHS.inc() # Увеличиваем счетчик успешных аутентификаций
                    # Временно используем response_message (который является токеном или ID сессии) как session_id
                    response_data = {"status": "success", "message": response_message, "session_id": response_message} 
                    logger.info(f"User '{username}' authenticated successfully. Response: {response_data}")
                else:
                    FAILED_AUTHS.inc() # Увеличиваем счетчик неудачных аутентификаций
                    response_data = {"status": "failure", "message": f"Authentication failed: {response_message}"} # Already translated in logs, message from authenticate_user is expected to be English
                    logger.warning(f"Failed authentication attempt for user '{username}'. Reason: {response_message}. Response: {response_data}")
            
            elif action == "register": # Если действие - "register"
                # Это mock-ответ для регистрации. В реальной системе здесь была бы логика регистрации.
                response_data = {"status": "success", "message": "Registration action received (mock response)"}
                logger.info(f"Received mock registration request for user '{username}'. Response: {response_data}")
            
            else: # Если действие неизвестно
                response_data = {"status": "error", "message": "Unknown or missing action"}
                logger.warning(f"Unknown or missing action '{action}' from {addr}. Response: {response_data}")

        # Обработка ошибки декодирования JSON.
        except json.JSONDecodeError as je:
            # message_json_str доступна здесь и содержит строку, вызвавшую ошибку.
            logger.error(f"Invalid JSON received from {addr}: '{message_json_str}' | Error: {je}. Raw bytes: {raw_data_bytes!r}")
            response_data = {"status": "error", "message": "Invalid JSON format"}
            # FAILED_AUTHS.inc() # Можно рассмотреть, считать ли это неудачной аутентификацией
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции

        # Отправка успешного ответа клиенту (если не было ошибок выше)
        writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
        await writer.drain()
        logger.debug(f"JSON response sent to client {addr}: {response_data}")
        # Явный блок закрытия удален, finally закроет соединение и уменьшит счетчик.
        # Нет return здесь, чтобы finally выполнился для ACTIVE_CONNECTIONS_AUTH.dec()

    except ConnectionResetError:
        logger.warning(f"Connection reset by client {addr}.")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    except asyncio.IncompleteReadError:
        logger.warning(f"Incomplete read from client {addr}. Connection might have been closed prematurely.")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    # Убедимся, что UnicodeDecodeError перехватывается перед общим Exception,
    # если ошибка декодирования произойдет вне внутреннего try-except.
    except UnicodeDecodeError as ude: 
        logger.error(f"Unicode decode error from {addr} (outer catch): {ude}. Raw data: {raw_data_bytes!r}")
        response_data = {"status":"error", "message":"Invalid character encoding. UTF-8 expected."}
        
        # Этот лог остается для отладки состояния writer
        logger.debug(f"In UnicodeDecodeError handler for {addr}: writer.is_closing() is {writer.is_closing()}") 
        
        if not writer.is_closing(): # Если writer еще не закрывается
            try:
                logger.debug(f"Attempting to send UnicodeDecodeError error response to client {addr}")
                writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"Successfully sent UnicodeDecodeError error response to client {addr}")
            except Exception as ex_send:
                logger.error(f"Failed to send JSON error message (UnicodeDecodeError) to client {addr}: {ex_send}")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    except Exception as e:
        # Логируем исключение с полным стектрейсом.
        logger.exception(f"General error processing client {addr}:")
        # FAILED_AUTHS.inc() # Можно засчитать как неудачу, если ошибка произошла до успешной аутентификации
        
        if not writer.is_closing(): # Если writer еще не закрывается
            try:
                # Гарантируем, что даже при общих ошибках пытаемся отправить JSON-ответ.
                error_response_data = {"status": "error", "message": "Internal server error"} # Already in English
                writer.write(json.dumps(error_response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"JSON error message sent to client {addr}: {error_response_data}")
            except Exception as ex_send:
                logger.error(f"Failed to send JSON error message to client {addr}: {ex_send}")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции после обработки общего исключения
    finally:
        # Блок finally гарантирует, что ресурсы будут освобождены.
        logger.debug(f"Entering finally block for {addr}, preparing to close writer.")
        logger.info(f"Closing connection with {addr}")
        ACTIVE_CONNECTIONS_AUTH.dec() # Уменьшаем счетчик активных соединений
        if not writer.is_closing(): # Проверяем, не закрывается ли writer уже
            logger.debug(f"Closing writer for {addr} in finally block.")
            writer.close() # Закрываем writer
            try:
                await writer.wait_closed() # Ожидаем полного закрытия
            except Exception as e_close:
                logger.error(f"Error waiting for writer to close for {addr}: {e_close}")
        logger.debug(f"Connection with {addr} fully closed.")
