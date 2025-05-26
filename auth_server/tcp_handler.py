# auth_server/tcp_handler.py
import asyncio
import json # Add json import
import logging # Добавляем импорт
from .user_service import authenticate_user
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def handle_auth_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info('peername')
    logger.info(f"Новое подключение от {addr}, ожидается JSON.")
    ACTIVE_CONNECTIONS_AUTH.inc()
    response_data = {} # Initialize response_data

    try:
        raw_data_bytes = await reader.readuntil(b'\n') # Читаем данные до символа новой строки
        
        if not raw_data_bytes or raw_data_bytes == b'\n': # Check for empty or newline-only
            logger.warning(f"Empty or newline-only message received from {addr} before decoding. Closing connection.")
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            return
            
        raw_data = raw_data_bytes.decode('utf-8', errors='ignore')
        # The subtask asks for raw_data.strip() and then check.
        # The existing code decodes, then strips, and assigns to message_json_str.
        # Let's keep message_json_str as the stripped version for minimal changes to subsequent code.
        
        message_json_str = raw_data.strip()
        
        if not message_json_str: # Check if message_json_str is empty AFTER stripping
            logger.warning(f"Empty message received from {addr} after strip. Sending error and closing.")
            response_data = {"status": "error", "message": "Empty message received"}
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()
            return

        try:
            # message_json_str is already decoded and stripped
            logger.debug(f"Получена строка JSON от {addr}: '{message_json_str}'")
            message_data = json.loads(message_json_str)
            action = message_data.get("action")
            username = message_data.get("username")
            password = message_data.get("password")

            logger.info(f"Получен action '{action}' от {addr} для пользователя '{username}'")

            if action == "login":
                is_authenticated, response_message = await authenticate_user(username, password)
                if is_authenticated:
                    SUCCESSFUL_AUTHS.inc()
                    response_data = {"status": "success", "message": response_message, "session_id": response_message} # Using message as session_id for now
                    logger.info(f"Пользователь '{username}' успешно аутентифицирован. Ответ: {response_data}")
                else:
                    FAILED_AUTHS.inc()
                    response_data = {"status": "failure", "message": f"Authentication failed: {response_message}"}
                    logger.warning(f"Неудачная попытка аутентификации для пользователя '{username}'. Причина: {response_message}. Ответ: {response_data}")
            
            elif action == "register":
                # Mock registration response
                response_data = {"status": "success", "message": "Registration action received (mock)"}
                logger.info(f"Получен mock-запрос на регистрацию для пользователя '{username}'. Ответ: {response_data}")
            
            else:
                response_data = {"status": "error", "message": "Unknown or missing action"}
                logger.warning(f"Неизвестное или отсутствующее действие '{action}' от {addr}. Ответ: {response_data}")

        except UnicodeDecodeError as ude:
            logger.error(f"Unicode decoding error from {addr}: {ude}. Raw data: {data!r}")
            response_data = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
            # FAILED_AUTHS.inc() # Consider if this should count as a failed auth
        except json.JSONDecodeError as je:
            # Updated log message to include raw 'data' bytes.
            # message_json_str is available here because UnicodeDecodeError would have been caught first if decoding failed.
            logger.error(f"Invalid JSON received from {addr}: '{message_json_str}' | Error: {je}. Raw bytes: {data!r}")
            response_data = {"status": "error", "message": "Invalid JSON format"}
            # FAILED_AUTHS.inc() # Consider if this should count as a failed auth

        writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
        await writer.drain()
        logger.debug(f"Отправлен JSON ответ клиенту {addr}: {response_data}")

    except ConnectionResetError:
        logger.warning(f"Соединение сброшено клиентом {addr}.")
    except asyncio.IncompleteReadError:
        logger.warning(f"Неполное чтение от клиента {addr}. Соединение могло быть закрыто преждевременно.")
    # Make sure UnicodeDecodeError is caught before generic Exception if it occurs outside the inner try-except
    except UnicodeDecodeError as ude: # This will catch decoding errors if data.decode() is moved outside the inner try
        logger.error(f"Unicode decoding error from {addr} (outer catch): {ude}. Raw data: {data!r}")
        response_data = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        if not writer.is_closing():
            try:
                writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"Не удалось отправить JSON сообщение об ошибке (UnicodeDecodeError) клиенту {addr}: {ex_send}")
    except Exception as e:
        logger.exception(f"Общая ошибка при обработке клиента {addr}:")
        # FAILED_AUTHS.inc() # Считаем это неудачей, если ошибка произошла до успешной аутентификации
        
        if not writer.is_closing():
            try:
                # Ensure even general errors try to send a JSON response
                error_response_data = {"status": "error", "message": "Internal server error"}
                writer.write(json.dumps(error_response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"Отправлено JSON сообщение об ошибке клиенту {addr}: {error_response_data}")
            except Exception as ex_send:
                logger.error(f"Не удалось отправить JSON сообщение об ошибке клиенту {addr}: {ex_send}")
    finally:
        logger.info(f"Закрытие соединения с {addr}")
        ACTIVE_CONNECTIONS_AUTH.dec()
        if not writer.is_closing(): # Check if writer is not already closing
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Ошибка при ожидании закрытия writer для {addr}: {e_close}")
        logger.debug(f"Соединение с {addr} полностью закрыто.")
