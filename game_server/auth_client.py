# game_server/auth_client.py
# Этот модуль содержит класс AuthClient, который отвечает за взаимодействие
# игрового сервера с сервером аутентификации.
import asyncio
import json # Добавлен импорт для работы с JSON
import logging # Добавлен импорт для логирования

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

class AuthClient:
    """
    Клиент для взаимодействия с сервером аутентификации.

    Позволяет отправлять команды (например, для входа пользователя) на сервер
    аутентификации и получать результаты.
    """
    def __init__(self, auth_server_host: str, auth_server_port: int, timeout: float = 5.0):
        """
        Инициализирует AuthClient.

        Args:
            auth_server_host (str): Хост сервера аутентификации.
            auth_server_port (int): Порт сервера аутентификации.
            timeout (float): Таймаут по умолчанию для сетевых операций (в секундах).
        """
        self.auth_host = auth_server_host
        self.auth_port = auth_server_port
        self.timeout = timeout # Таймаут для сетевых операций (в секундах).

    async def _send_auth_command(self, command_dict: dict):
        """
        Отправляет команду в формате JSON на сервер аутентификации и получает ответ.

        Это внутренний метод, используемый другими методами клиента.

        Args:
            command_dict (dict): Словарь с командой и данными для отправки.

        Returns:
            tuple[str, str, str|None]: Кортеж со статусом ответа ("AUTH_SUCCESS" или "AUTH_FAILURE"),
                                       сообщением от сервера и токеном сессии (если есть).
        """
        reader = None
        writer = None
        try:
            logger.debug(f"AuthClient: Attempting to connect to {self.auth_host}:{self.auth_port} with timeout {self.timeout}s.")
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.auth_host, self.auth_port),
                timeout=self.timeout
            )
            logger.info(f"AuthClient: Successfully connected to authentication server at {self.auth_host}:{self.auth_port}.")
        except asyncio.TimeoutError:
            error_msg = f"AuthClient: Таймаут при попытке подключения к серверу аутентификации по адресу {self.auth_host}:{self.auth_port} (таймаут: {self.timeout}с)."
            logger.error(error_msg)
            return "AUTH_FAILURE", error_msg, None
        except ConnectionRefusedError:
            error_msg = f"AuthClient: Сервер аутентификации по адресу {self.auth_host}:{self.auth_port} отказал в соединении."
            logger.error(error_msg)
            return "AUTH_FAILURE", error_msg, None
        except OSError as e: # Перехватывает socket.gaierror и другие сетевые ошибки уровня ОС
            error_msg = f"AuthClient: Сетевая ошибка при подключении к серверу аутентификации по адресу {self.auth_host}:{self.auth_port}: {e}"
            logger.error(error_msg, exc_info=True) # Включаем трассировку стека для OSError
            return "AUTH_FAILURE", error_msg, None
        except Exception as e: # Перехват других неожиданных ошибок во время подключения
            error_msg = f"AuthClient: Неожиданная ошибка при подключении к серверу аутентификации по адресу {self.auth_host}:{self.auth_port}: {e}"
            logger.error(error_msg, exc_info=True)
            return "AUTH_FAILURE", error_msg, None

        response_str = ""
        try:
            json_payload_str = json.dumps(command_dict)
            json_payload_bytes = json_payload_str.encode('utf-8')
            logger.debug(f"AuthClient: Sending to {self.auth_host}:{self.auth_port}: {json_payload_str}")

            writer.write(json_payload_bytes + b"\n")
            await asyncio.wait_for(writer.drain(), timeout=self.timeout) # Добавлен таймаут для drain
            logger.debug(f"AuthClient: Data drained to {self.auth_host}:{self.auth_port}.")

            response_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=self.timeout) # Используется self.timeout, было 10.0
            response_str = response_data.decode('utf-8').strip()
            logger.info(f"AuthClient: Response from {self.auth_host}:{self.auth_port}: {response_str}")

        except asyncio.TimeoutError:
            error_msg = f"AuthClient: Таймаут во время операции (drain или read) с сервером аутентификации {self.auth_host}:{self.auth_port} (таймаут: {self.timeout}с)."
            logger.error(error_msg)
            # response_str остается пустым или частично заполненным, ошибка обрабатывается при разборе JSON ниже
            return "AUTH_FAILURE", error_msg, None # Ранний возврат при таймауте операции
        except asyncio.IncompleteReadError as e:
            error_msg = f"AuthClient: Сервер аутентификации {self.auth_host}:{self.auth_port} преждевременно закрыл соединение. Частичные данные: {e.partial!r}"
            logger.error(error_msg)
            return "AUTH_FAILURE", error_msg, None # Ранний возврат
        except OSError as e: # Перехват возможных ошибок во время write/drain/read, если соединение обрывается
            error_msg = f"AuthClient: Сетевая ошибка во время обмена данными с {self.auth_host}:{self.auth_port}: {e}"
            logger.error(error_msg, exc_info=True)
            return "AUTH_FAILURE", error_msg, None
        except Exception as e: # Перехват других неожиданных ошибок во время обмена данными
            error_msg = f"AuthClient: Неожиданная ошибка во время обмена данными с {self.auth_host}:{self.auth_port}: {e}"
            logger.error(error_msg, exc_info=True)
            return "AUTH_FAILURE", error_msg, None # Ранний возврат
        finally:
            if writer: # Убедимся, что writer существует, прежде чем пытаться закрыть
                logger.debug(f"AuthClient: Closing connection to {self.auth_host}:{self.auth_port}.")
                writer.close()
                try:
                    await writer.wait_closed()
                    logger.debug(f"AuthClient: Connection to {self.auth_host}:{self.auth_port} closed.")
                except Exception as e_close: # Логируем, если wait_closed по какой-то причине не удался
                    logger.error(f"AuthClient: Error during writer.wait_closed() for {self.auth_host}:{self.auth_port}: {e_close}", exc_info=True)

        # Парсим JSON-ответ (Эта часть достигается только в случае успешного обмена данными)
        try:
            response_json = json.loads(response_str)
            status_from_auth_server = response_json.get("status")
            message_from_auth_server = response_json.get("message", "Поле 'message' отсутствует в JSON-ответе.")

            # Стандартизируем статус для пользователей AuthClient
            if status_from_auth_server == "success":
                status_to_return = "AUTH_SUCCESS"
            elif status_from_auth_server == "failure":
                status_to_return = "AUTH_FAILURE"
            else: # Неизвестный статус в JSON
                status_to_return = "AUTH_FAILURE"
                message_from_auth_server = f"Неизвестный статус '{status_from_auth_server}' в ответе сервера аутентификации. Полный ответ: {response_str}"
            
            final_message = message_from_auth_server

        except json.JSONDecodeError:
            logger.error(f"AuthClient: JSON decode error when parsing response from authentication server: '{response_str}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "Неверный JSON-ответ от сервера аутентификации."
            response_json = None # Убедимся, что response_json - None при ошибке
        except AttributeError: # Если response_json не словарь (например, json.loads вернул строку/список)
            logger.error(f"AuthClient: AttributeError, response_json is not a dictionary. Response: '{response_str}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "JSON-ответ от сервера аутентификации не является словарем."
            response_json = None

        session_token = None 
        # Пример извлечения токена в будущем, если сервер аутентификации будет его возвращать в JSON:
        if status_to_return == "AUTH_SUCCESS" and isinstance(response_json, dict):
           session_token = response_json.get("session_id") # Предполагаем, что сервер возвращает session_id

        logger.debug(f"AuthClient._send_auth_command returns: status='{status_to_return}', message='{final_message}', token='{session_token}'")
        return status_to_return, final_message, session_token


    async def login_user(self, username, password):
        """
        Отправляет команду LOGIN на сервер аутентификации для входа пользователя.

        Args:
            username (str): Имя пользователя.
            password (str): Пароль пользователя.

        Returns:
            tuple[bool, str, str|None]: Кортеж, где первый элемент - булево значение
                                       (True при успехе, False при неудаче), второй -
                                       сообщение от сервера, третий - токен сессии
                                       (может быть None, если аутентификация не удалась
                                       или сервер не вернул токен).
        """
        command_dict = {"action": "login", "username": username, "password": password}
        status, message, session_token = await self._send_auth_command(command_dict)
        
        authenticated = (status == "AUTH_SUCCESS")
        
        # В текущей реализации сервер аутентификации может не возвращать токен напрямую
        # в login_user, а только статус. Токен может быть частью 'message' или отдельным полем.
        # Здесь мы просто передаем токен, полученный из _send_auth_command.
        if authenticated:
            logger.info(f"User '{username}' successfully authenticated via AuthClient. Token: {session_token}")
            return True, message, session_token 
        
        logger.warning(f"Failed authentication for user '{username}' via AuthClient. Message: {message}")
        return False, message, None

    # Закомментированные методы ниже - примеры возможных будущих функций клиента.
    # async def register_user(self, username, password):
    #     """
    #     Отправляет команду REGISTER на сервер аутентификации.
    #     (Пока не используется активно в текущей логике игрового сервера)
    #     Возвращает (bool, str): (успех, сообщение)
    #     """
    #     # command_dict = {"action": "register", "username": username, "password": password}
    #     # status, message, _ = await self._send_auth_command(command_dict) # Токен не ожидается при регистрации
    #     # return status == "AUTH_SUCCESS", message # Предполагая, что сервер вернет AUTH_SUCCESS
    #     pass
    #
    # async def validate_token(self, token: str):
    #     """
    #     Отправляет команду VALIDATE_TOKEN на сервер аутентификации.
    #     (Пока не используется)
    #     Возвращает (bool, str): (валидность_токена, сообщение)
    #     """
    #     # command_dict = {"action": "validate_token", "token": token}
    #     # status, message, _ = await self._send_auth_command(command_dict)
    #     # return status == "AUTH_SUCCESS", message # Предполагая, что сервер вернет AUTH_SUCCESS при валидном токене
    #     pass
    pass # Конец класса AuthClient
