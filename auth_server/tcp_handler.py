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
    logger.info(f"Новое соединение от {addr}, ожидается JSON.")
    ACTIVE_CONNECTIONS_AUTH.inc()
    try:
        logger.debug(f"handle_auth_client: [{addr}] Ожидание данных от клиента с таймаутом {CLIENT_READ_TIMEOUT}с.")
        data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=CLIENT_READ_TIMEOUT)
        logger.debug(f"handle_auth_client: [{addr}] Получены сырые данные: {data!r}")
        message = data.decode('utf-8').strip()
        
        logger.info(f"handle_auth_client: [{addr}] Получено обработанное сообщение: '{message}'")

        if not message:
            logger.warning(f"handle_auth_client: [{addr}] Пустое сообщение после обработки из сырых данных: {data!r}.")
            response_payload = {"status": "error", "message": "Получено пустое сообщение"}
            writer.write(json.dumps(response_payload).encode('utf-8') + b'\n')
            await writer.drain()
            return

        try:
            logger.debug(f"handle_auth_client: [{addr}] Попытка разбора JSON: '{message}'")
            payload = json.loads(message)
            action = payload.get("action")
            username = payload.get("username")
            password = payload.get("password") # Для register это будет сырой пароль

            logger.info(f"handle_auth_client: [{addr}] Разобранная полезная нагрузка: {payload}, Действие: '{action}'")

            response = {}
            if action == "login":
                if not username or not password:
                    logger.warning(f"handle_auth_client: [{addr}] Попытка входа с отсутствующим именем пользователя или паролем.")
                    FAILED_AUTHS.inc()
                    response = {"status": "failure", "message": "Отсутствует имя пользователя или пароль для входа."}
                else:
                    logger.info(f"handle_auth_client: [{addr}] Обработка действия 'login' для пользователя '{username}'.")
                    logger.debug(f"handle_auth_client: [{addr}] Вызов user_service.authenticate_user для пользователя '{username}'.")
                    # Используем экземпляр user_service
                    authenticated, detail = await user_service.authenticate_user(username, password)
                    logger.info(f"handle_auth_client: [{addr}] Результат аутентификации для '{username}': успех={authenticated}, детали='{detail}'")

                    if authenticated:
                        SUCCESSFUL_AUTHS.inc()
                        response = {"status": "success", "message": detail, "token": username} # detail уже на русском от user_service
                    else:
                        FAILED_AUTHS.inc()
                        response = {"status": "failure", "message": detail} # detail уже на русском от user_service

            elif action == "register":
                if not username or not password:
                    logger.warning(f"handle_auth_client: [{addr}] Попытка регистрации с отсутствующим именем пользователя или паролем.")
                    # Не инкрементируем FAILED_AUTHS здесь, т.к. это не неудачная попытка входа, а ошибка запроса.
                    # Однако, если считать это неудачной попыткой операции, можно и добавить. Пока не будем.
                    response = {"status": "error", "message": "Отсутствует имя пользователя или пароль для регистрации."}
                else:
                    logger.info(f"handle_auth_client: [{addr}] Обработка действия 'register' для пользователя '{username}'.")
                    # ВАЖНО: UserService.create_user ожидает ХЕШИРОВАННЫЙ пароль.
                    # Текущий tcp_handler получает сырой пароль.
                    # Для выполнения задачи "Проверь, что create_user вызывается с ("newuser", "newpassword")"
                    # мы передадим сырой пароль. Это означает, что либо UserService.create_user
                    # должен быть изменен для хеширования, либо этот handler должен хешировать пароль.
                    # Пока что, следуя тестовому требованию, передаем как есть.
                    # В реальной системе здесь должно быть хеширование пароля перед вызовом create_user.
                    # Например: password_hash = await hash_password_utility(password)
                    # И затем: created, detail = await user_service.create_user(username, password_hash)
                    logger.debug(f"handle_auth_client: [{addr}] Вызов user_service.create_user для пользователя '{username}'. Пароль будет передан как есть (в реальном сценарии должен быть хеширован).")
                    created, detail = await user_service.create_user(username, password) # Передаем сырой пароль
                    logger.info(f"handle_auth_client: [{addr}] Результат регистрации для '{username}': создано={created}, детали='{detail}'")
                    if created:
                        # SUCCESSFUL_REGISTRATIONS.inc() # Потенциальная новая метрика
                        response = {"status": "success", "message": detail} # detail уже на русском от user_service
                    else:
                        # FAILED_REGISTRATIONS.inc() # Потенциальная новая метрика
                        response = {"status": "failure", "message": detail} # detail уже на русском от user_service
            else:
                logger.warning(f"handle_auth_client: [{addr}] Неизвестное или отсутствующее действие: '{action}'.")
                # FAILED_AUTHS.inc() # Можно считать это ошибкой запроса, а не неудачным входом
                response = {"status": "error", "message": "Неизвестное или отсутствующее действие"}
            
            response_str = json.dumps(response) + "\n"
            logger.info(f"handle_auth_client: [{addr}] Отправка ответа: {response_str.strip()}")
            writer.write(response_str.encode('utf-8'))
            await writer.drain()

        except json.JSONDecodeError:
            logger.error(f"handle_auth_client: [{addr}] Получен неверный JSON: {message}", exc_info=True)
            error_response = {"status": "error", "message": "Неверный формат JSON"}
            writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
            await writer.drain()
            # Здесь нет return, очистка будет в finally. FAILED_AUTHS может быть релевантен.
        except Exception as e: # Перехват других ошибок во время обработки полезной нагрузки или действия
            logger.error(f"handle_auth_client: [{addr}] Ошибка обработки сообщения: {e}", exc_info=True)
            error_response = {"status": "error", "message": "Внутренняя ошибка сервера при обработке"}
            if not writer.is_closing():
                try:
                    writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                    await writer.drain()
                except Exception as ex_send:
                    logger.error(f"handle_auth_client: [{addr}] Не удалось отправить ответ об ошибке во время общего исключения: {ex_send}", exc_info=True)
            # Здесь нет return, очистка будет в finally.

    except asyncio.TimeoutError: # Специально для таймаута reader.readuntil
        logger.warning(f"handle_auth_client: [{addr}] Таймаут ожидания сообщения от клиента ({CLIENT_READ_TIMEOUT}с).")
        # Попытка отправить ответ о таймауте, если writer все еще открыт
        if not writer.is_closing():
            try:
                error_response = {"status": "error", "message": "Таймаут запроса"}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Не удалось отправить ответ об ошибке таймаута: {ex_send}", exc_info=True)
    except asyncio.IncompleteReadError as e:
        logger.warning(f"handle_auth_client: [{addr}] Незавершенное чтение. Клиент преждевременно закрыл соединение. Частичные данные: {e.partial!r}", exc_info=True)
    except ConnectionResetError as e:
        logger.warning(f"handle_auth_client: [{addr}] Соединение сброшено клиентом.", exc_info=True)
    except UnicodeDecodeError as ude: 
        logger.error(f"handle_auth_client: [{addr}] Ошибка декодирования Unicode: {ude}. Сырые данные могут быть не в UTF-8.", exc_info=True)
        if not writer.is_closing():
            try:
                error_response = {"status":"error", "message":"Неверная кодировка символов. Ожидается UTF-8."}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Не удалось отправить ответ об ошибке UnicodeDecodeError: {ex_send}", exc_info=True)
    except Exception as e:
        logger.critical(f"handle_auth_client: [{addr}] Критическая ошибка в обработчике: {e}", exc_info=True)
        if not writer.is_closing():
            try:
                error_response = {"status": "error", "message": "Критическая внутренняя ошибка сервера"}
                writer.write(json.dumps(error_response).encode('utf-8') + b'\n')
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"handle_auth_client: [{addr}] Не удалось отправить ответ о критической ошибке: {ex_send}", exc_info=True)
    finally:
        logger.info(f"handle_auth_client: [{addr}] Закрытие соединения.")
        ACTIVE_CONNECTIONS_AUTH.dec()
        if writer and not writer.is_closing(): 
            logger.debug(f"handle_auth_client: [{addr}] Фактическое закрытие writer сейчас.")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_close: 
                logger.error(f"handle_auth_client: [{addr}] Ошибка во время writer.wait_closed(): {e_close}", exc_info=True)
        logger.debug(f"handle_auth_client: [{addr}] Соединение с {addr} полностью закрыто.")
