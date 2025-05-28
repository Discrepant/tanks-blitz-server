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
    def __init__(self, auth_server_host: str, auth_server_port: int):
        """
        Инициализирует AuthClient.

        Args:
            auth_server_host (str): Хост сервера аутентификации.
            auth_server_port (int): Порт сервера аутентификации.
        """
        self.auth_host = auth_server_host
        self.auth_port = auth_server_port

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
        try:
            # Устанавливаем соединение с сервером аутентификации
            reader, writer = await asyncio.open_connection(self.auth_host, self.auth_port)
        except ConnectionRefusedError:
            error_msg = f"Failed to connect to authentication server at {self.auth_host}:{self.auth_port}. Server unavailable."
            logger.error(error_msg)
            return "AUTH_FAILURE", error_msg, None # Возвращаем None для токена
        except Exception as e:
            error_msg = f"Unknown error when connecting to authentication server: {e}"
            logger.error(error_msg, exc_info=True)
            return "AUTH_FAILURE", error_msg, None # Возвращаем None для токена

        # Сериализуем команду в JSON и кодируем в байты
        json_payload_str = json.dumps(command_dict)
        json_payload_bytes = json_payload_str.encode('utf-8')
        logger.debug(f"Sending to authentication server ({self.auth_host}:{self.auth_port}): {json_payload_str}")
        writer.write(json_payload_bytes + b"\n") # Добавляем символ новой строки как разделитель
        await writer.drain() # Ожидаем отправки данных

        response_str = "" # Инициализируем строку ответа
        try:
            # Читаем ответ от сервера с таймаутом
            response_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
            response_str = response_data.decode().strip()
            logger.info(f"Response from authentication server: {response_str}")
        except asyncio.TimeoutError:
            logger.error(f"AuthClient: Response from authentication server ({self.auth_host}:{self.auth_port}) not received (timeout).")
            # response_str остается пустым, обработка ошибки произойдет ниже при парсинге JSON
        except asyncio.IncompleteReadError:
            logger.error(f"AuthClient: Authentication server ({self.auth_host}:{self.auth_port}) closed connection without full response.")
            # response_str остается пустым
        except Exception as e:
            logger.error(f"AuthClient: Error reading response from authentication server ({self.auth_host}:{self.auth_port}): {e}", exc_info=True)
            # response_str остается пустым
        finally:
            # Закрываем соединение
            writer.close()
            await writer.wait_closed()

        # Парсим JSON-ответ
        try:
            response_json = json.loads(response_str)
            status_from_auth_server = response_json.get("status")
            message_from_auth_server = response_json.get("message", "Message field is missing in JSON response.")

            # Стандартизируем статус для пользователей AuthClient
            if status_from_auth_server == "success":
                status_to_return = "AUTH_SUCCESS"
            elif status_from_auth_server == "failure":
                status_to_return = "AUTH_FAILURE"
            else: # Неизвестный статус в JSON
                status_to_return = "AUTH_FAILURE"
                message_from_auth_server = f"Unknown status '{status_from_auth_server}' in authentication server response. Full response: {response_str}"
            
            final_message = message_from_auth_server

        except json.JSONDecodeError:
            logger.error(f"AuthClient: JSON decode error when parsing response from authentication server: '{response_str}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "Invalid JSON response from authentication server."
            response_json = None # Убедимся, что response_json - None при ошибке
        except AttributeError: # Если response_json не словарь (например, json.loads вернул строку/список)
            logger.error(f"AuthClient: AttributeError, response_json is not a dictionary. Response: '{response_str}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "Non-dictionary JSON response from authentication server."
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
    #     (Пока не используется активно в текущей логике гейм-сервера)
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
