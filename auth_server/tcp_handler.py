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
        
        if not raw_data_bytes: # Check for empty or newline-only - MODIFIED
            logger.warning(f"Empty or newline-only message received from {addr} before decoding. Closing connection.")
            if not writer.is_closing():
                logger.debug(f"Explicitly closing writer for {addr} in 'if not raw_data_bytes' block.")
                writer.close() # wait_closed removed
            return
            
        raw_data = raw_data_bytes.decode('utf-8') # MODIFIED to strict decoding
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
                logger.debug(f"Explicitly closing writer for {addr} in 'if not message_json_str' block.")
                writer.close() # wait_closed removed
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

        # UnicodeDecodeError is now handled by the outer try-except due to strict decoding
        except json.JSONDecodeError as je:
            # message_json_str is available here
            logger.error(f"Invalid JSON received from {addr}: '{message_json_str}' | Error: {je}. Raw bytes: {raw_data_bytes!r}") # MODIFIED to use raw_data_bytes
            response_data = {"status": "error", "message": "Invalid JSON format"}
            # FAILED_AUTHS.inc() # Consider if this should count as a failed auth
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            if not writer.is_closing():
                logger.debug(f"Explicitly closing writer for {addr} in json.JSONDecodeError block.")
                writer.close() # wait_closed removed
            return

        # This is the successful path write
        writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
        await writer.drain()
        logger.debug(f"Отправлен JSON ответ клиенту {addr}: {response_data}")
        # Explicitly close after successful send, before finally block
        if not writer.is_closing():
            logger.debug(f"Explicitly closing writer for {addr} after successful response.")
            writer.close() # wait_closed removed
        # No return here, allow finally to execute for ACTIVE_CONNECTIONS_AUTH.dec()

    except ConnectionResetError:
        logger.warning(f"Соединение сброшено клиентом {addr}.")
        # Ensure connection is closed if reset happens before explicit close
        if not writer.is_closing():
            logger.debug(f"Explicitly closing writer for {addr} in ConnectionResetError block.")
            writer.close() # wait_closed and try-except removed
        return
    except asyncio.IncompleteReadError:
        logger.warning(f"Неполное чтение от клиента {addr}. Соединение могло быть закрыто преждевременно.")
        # Adding explicit close and debug log here as well, as it's an early exit path
        if not writer.is_closing():
            logger.debug(f"Explicitly closing writer for {addr} in asyncio.IncompleteReadError block.")
            writer.close() # wait_closed and try-except removed
        return
    # Make sure UnicodeDecodeError is caught before generic Exception if it occurs outside the inner try-except
    except UnicodeDecodeError as ude: # This will catch decoding errors if data.decode() is moved outside the inner try
        logger.error(f"Unicode decoding error from {addr} (outer catch): {ude}. Raw data: {raw_data_bytes!r}")
        response_data = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        
        logger.debug(f"In UnicodeDecodeError handler for {addr}: writer.is_closing() is {writer.is_closing()}") # New log line
        
        if not writer.is_closing():
            try:
                logger.debug(f"Attempting to send UnicodeDecodeError response to {addr}")
                writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"Successfully sent UnicodeDecodeError response to {addr}")
            except Exception as ex_send:
                logger.error(f"Не удалось отправить JSON сообщение об ошибке (UnicodeDecodeError) клиенту {addr}: {ex_send}")
        if not writer.is_closing():
            logger.debug(f"Explicitly closing writer for {addr} in UnicodeDecodeError (outer) block.")
            writer.close() # wait_closed removed
        return
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
        # Ensure close even in general exception case
        if not writer.is_closing():
            logger.debug(f"Explicitly closing writer for {addr} in general Exception block.")
            writer.close() # wait_closed and try-except removed
        return # Return after handling general exception
    finally:
        logger.debug(f"Entering finally block for {addr}, preparing to ensure writer is closed.") # Added debug log
        logger.info(f"Закрытие соединения с {addr}")
        ACTIVE_CONNECTIONS_AUTH.dec()
        if not writer.is_closing(): # Check if writer is not already closing
            logger.debug(f"Closing writer for {addr} in finally block.") # Added debug log
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"Ошибка при ожидании закрытия writer для {addr}: {e_close}")
        logger.debug(f"Соединение с {addr} полностью закрыто.")
