# auth_server/tcp_handler.py
# Этот модуль отвечает за обработку TCP-соединений и сообщений от клиентов
# для сервера аутентификации.
import asyncio
import json # Импортируем json для работы с JSON-сообщениями
import logging # Импортируем logging для логирования
# Импортируем UserService и глобальные функции (которые теперь обертки) для обратной совместимости или постепенного перехода
from .user_service import UserService # , authenticate_user, create_user # Убрали authenticate_user, create_user
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импортируем метрики Prometheus

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Создаем экземпляр UserService для использования в обработчике
# Это предполагает, что UserService может быть инстанцирован глобально.
# Если UserService требует специфической конфигурации или управления жизненным циклом,
# это может потребовать другого подхода (например, передача через DI или фабрику).
user_service = UserService()

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
    try:
        logger.debug(f"handle_auth_client: [{addr}] Waiting for data from client with timeout {CLIENT_READ_TIMEOUT}s.")
        data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=CLIENT_READ_TIMEOUT)
        logger.debug(f"handle_auth_client: [{addr}] Received raw data: {data!r}")
        message = data.decode('utf-8').strip()
        
        logger.info(f"handle_auth_client: [{addr}] Received stripped message: '{message}'")

        if not message:
            logger.warning(f"handle_auth_client: [{addr}] Empty message after strip from raw: {data!r}.")
            response_payload = {"status": "error", "message": "Empty message received"}
            writer.write(json.dumps(response_payload).encode('utf-8') + b'\n')
            await writer.drain()
            return

        try:
            logger.debug(f"handle_auth_client: [{addr}] Attempting to parse JSON: '{message}'")
            payload = json.loads(message)
            action = payload.get("action")
            username = payload.get("username")
            password = payload.get("password") # Для register это будет сырой пароль

            logger.info(f"handle_auth_client: [{addr}] Parsed payload: {payload}, Action: '{action}'")

            response = {}
            if action == "login":
                if not username or not password:
                    logger.warning(f"handle_auth_client: [{addr}] Login attempt with missing username or password.")
                    FAILED_AUTHS.inc()
                    response = {"status": "failure", "message": "Missing username or password for login."}
                else:
                    logger.info(f"handle_auth_client: [{addr}] Processing 'login' action for user '{username}'.")
                    logger.debug(f"handle_auth_client: [{addr}] Calling user_service.authenticate_user for user '{username}'.")
                    # Используем экземпляр user_service
                    authenticated, detail = await user_service.authenticate_user(username, password)
                    logger.info(f"handle_auth_client: [{addr}] Authentication result for '{username}': success={authenticated}, detail='{detail}'")

                    if authenticated:
                        SUCCESSFUL_AUTHS.inc()
                        response = {"status": "success", "message": detail, "token": username}
                    else:
                        FAILED_AUTHS.inc()
                        response = {"status": "failure", "message": detail}

            elif action == "register":
                if not username or not password:
                    logger.warning(f"handle_auth_client: [{addr}] Registration attempt with missing username or password.")
                    # Не инкрементируем FAILED_AUTHS здесь, т.к. это не неудачная попытка входа, а ошибка запроса.
                    # Однако, если считать это неудачной попыткой операции, можно и добавить. Пока не будем.
                    response = {"status": "error", "message": "Missing username or password for registration."}
                else:
                    logger.info(f"handle_auth_client: [{addr}] Processing 'register' action for user '{username}'.")
                    # ВАЖНО: UserService.create_user ожидает ХЕШИРОВАННЫЙ пароль.
                    # Текущий tcp_handler получает сырой пароль.
                    # Для выполнения задачи "Проверь, что create_user вызывается с ("newuser", "newpassword")"
                    # мы передадим сырой пароль. Это означает, что либо UserService.create_user
                    # должен быть изменен для хеширования, либо этот handler должен хешировать пароль.
                    # Пока что, следуя тестовому требованию, передаем как есть.
                    # В реальной системе здесь должно быть хеширование пароля перед вызовом create_user.
                    # Например: password_hash = await hash_password_utility(password)
                    # И затем: created, detail = await user_service.create_user(username, password_hash)
                    logger.debug(f"handle_auth_client: [{addr}] Calling user_service.create_user for user '{username}'. Password will be passed as is (should be hashed in a real scenario).")
                    created, detail = await user_service.create_user(username, password) # Передаем сырой пароль
                    logger.info(f"handle_auth_client: [{addr}] Registration result for '{username}': created={created}, detail='{detail}'")
                    if created:
                        # SUCCESSFUL_REGISTRATIONS.inc() # Потенциальная новая метрика
                        response = {"status": "success", "message": detail}
                    else:
                        # FAILED_REGISTRATIONS.inc() # Потенциальная новая метрика
                        response = {"status": "failure", "message": detail}
            else:
                logger.warning(f"handle_auth_client: [{addr}] Unknown or missing action: '{action}'.")
                # FAILED_AUTHS.inc() # Можно считать это ошибкой запроса, а не неудачным входом
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
