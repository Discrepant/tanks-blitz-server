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

# Таймаут для операции чтения от клиента
CLIENT_READ_TIMEOUT = 15.0 # секунд

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
    ACTIVE_CONNECTIONS_AUTH.inc() 
    # response_data = {} # Not used here anymore, response is built per case
    # logger.info(f"handle_auth_client: [{addr}] Entered try block.") # Replaced by New connection log
    try:
        logger.debug(f"handle_auth_client: [{addr}] Waiting for data from client with timeout {CLIENT_READ_TIMEOUT}s.")
        data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=CLIENT_READ_TIMEOUT)
        logger.debug(f"handle_auth_client: [{addr}] Received raw data: {data!r}") # Log raw data
        message = data.decode('utf-8').strip()
        
        logger.info(f"handle_auth_client: [{addr}] Received stripped message: '{message}'")

        if not message:
            logger.warning(f"handle_auth_client: [{addr}] Empty message after strip from raw: {data!r}.")
            response_payload = {"status": "error", "message": "Empty message received"}
            writer.write(json.dumps(response_payload).encode('utf-8') + b'\n')
            await writer.drain()
            # Still want to go to finally for proper closure
            return

        try:
            logger.debug(f"handle_auth_client: [{addr}] Attempting to parse JSON: '{message}'")
            payload = json.loads(message)
            action = payload.get("action")
            username = payload.get("username") 
            password = payload.get("password") 

            logger.info(f"handle_auth_client: [{addr}] Parsed payload: {payload}, Action: '{action}'")

            response = {} # Renamed from response_data for clarity within this block
            if action == "login":
                logger.info(f"handle_auth_client: [{addr}] Processing 'login' action for user '{username}'.")
                
                logger.debug(f"handle_auth_client: [{addr}] Calling user_service.authenticate_user for user '{username}'.")
                # The import `from .user_service import authenticate_user` is at the top of the module.
                authenticated, detail = await authenticate_user(username, password) # authenticate_user is async
                logger.info(f"handle_auth_client: [{addr}] Authentication result for '{username}': success={authenticated}, detail='{detail}'")

                if authenticated:
                    SUCCESSFUL_AUTHS.inc()
                    response = {"status": "success", "message": detail, "token": username} 
                else:
                    FAILED_AUTHS.inc()
                    response = {"status": "failure", "message": detail}
            
            elif action == "register": 
                # This is a mock-response for registration.
                logger.info(f"handle_auth_client: [{addr}] Processing 'register' action for user '{username}'.")
                response = {"status": "success", "message": "Registration action received (mock response)"}
                logger.info(f"handle_auth_client: [{addr}] Mock registration for '{username}'. Response: {response}")

            else:
                logger.warning(f"handle_auth_client: [{addr}] Unknown or missing action: '{action}'.")
                response = {"status": "error", "message": "Unknown or missing action"}
            
            response_str = json.dumps(response) + "\n"
            logger.info(f"handle_auth_client: [{addr}] Sending response: {response_str.strip()}")
            writer.write(response_str.encode('utf-8'))
            await writer.drain()

        except json.JSONDecodeError:
            logger.error(f"handle_auth_client: [{addr}] Invalid JSON received: {message}", exc_info=True)
            error_response = {"status": "error", "message": "Invalid JSON format"}
            writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
            await writer.drain()
            # No return here, let finally handle cleanup. FAILED_AUTHS might be relevant.
        except Exception as e: # Catch other errors during payload processing or action handling
            logger.error(f"handle_auth_client: [{addr}] Error processing message: {e}", exc_info=True)
            error_response = {"status": "error", "message": "Internal server error during processing"}
            if not writer.is_closing():
                try:
                    writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                    await writer.drain()
                except Exception as ex_send:
                    logger.error(f"handle_auth_client: [{addr}] Failed to send error response during general exception: {ex_send}", exc_info=True)
            # No return here, let finally handle cleanup.

    except asyncio.TimeoutError: # Specifically for reader.readuntil timeout
        logger.warning(f"handle_auth_client: [{addr}] Timeout waiting for client message ({CLIENT_READ_TIMEOUT}s).")
        # Attempt to send timeout response if writer is still open
        if not writer.is_closing():
            try:
                error_response = {"status": "error", "message": "Request timeout"}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Failed to send timeout error response: {ex_send}", exc_info=True)
    except asyncio.IncompleteReadError as e:
        logger.warning(f"handle_auth_client: [{addr}] Incomplete read. Client closed connection prematurely. Partial data: {e.partial!r}", exc_info=True)
    except ConnectionResetError as e:
        logger.warning(f"handle_auth_client: [{addr}] Connection reset by client.", exc_info=True)
    except UnicodeDecodeError as ude: 
        logger.error(f"handle_auth_client: [{addr}] Unicode decode error: {ude}. Raw data might not be UTF-8.", exc_info=True)
        if not writer.is_closing():
            try:
                error_response = {"status":"error", "message":"Invalid character encoding. UTF-8 expected."}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Failed to send UnicodeDecodeError response: {ex_send}", exc_info=True)
    except Exception as e:
        logger.critical(f"handle_auth_client: [{addr}] Critical error in handler: {e}", exc_info=True)
        if not writer.is_closing():
            try:
                error_response = {"status": "error", "message": "Critical internal server error"}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Failed to send critical error response: {ex_send}", exc_info=True)
    finally:
        logger.info(f"handle_auth_client: [{addr}] Closing connection.")
        ACTIVE_CONNECTIONS_AUTH.dec()
        if writer and not writer.is_closing(): 
            logger.debug(f"handle_auth_client: [{addr}] Actually closing writer now.")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_close: 
                logger.error(f"handle_auth_client: [{addr}] Error during writer.wait_closed(): {e_close}", exc_info=True)
        logger.debug(f"handle_auth_client: [{addr}] Connection with {addr} fully closed.")
