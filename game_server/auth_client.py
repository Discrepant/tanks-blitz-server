import asyncio
import json # Added import
import logging # Added import

logger = logging.getLogger(__name__) # Added logger

class AuthClient:
    def __init__(self, auth_server_host: str, auth_server_port: int):
        self.auth_host = auth_server_host
        self.auth_port = auth_server_port

    async def _send_auth_command(self, command_dict: dict): # command is now a dict
        try:
            reader, writer = await asyncio.open_connection(self.auth_host, self.auth_port)
        except ConnectionRefusedError:
            error_msg = f"Не удалось подключиться к серверу аутентификации по адресу {self.auth_host}:{self.auth_port}. Сервер недоступен."
            print(error_msg)
            return "AUTH_FAILURE", error_msg, None # Добавляем None для токена
        except Exception as e:
            error_msg = f"Неизвестная ошибка при подключении к серверу аутентификации: {e}"
            print(error_msg)
            return "AUTH_FAILURE", error_msg, None # Добавляем None для токена


        json_payload_str = json.dumps(command_dict)
        json_payload_bytes = json_payload_str.encode('utf-8')
        print(f"Отправка на сервер аутентификации ({self.auth_host}:{self.auth_port}): {json_payload_str}")
        writer.write(json_payload_bytes + b"\n") # Добавляем \n
        await writer.drain()

        try:
            # Увеличиваем буфер и добавляем таймаут
            response_data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=10.0)
            response = response_data.decode().strip()
            logger.info(f"Ответ от сервера аутентификации: {response}") # Changed print to logger.info
        except asyncio.TimeoutError:
            logger.error("AuthClient: Ответ от сервера аутентификации не получен (таймаут).") # Changed print to logger.error
            response = "" # Ensure response is an empty string for consistent error handling below
            # Fall through to JSON parsing which will fail and set generic error message
        except asyncio.IncompleteReadError:
            logger.error("AuthClient: Сервер аутентификации закрыл соединение без полного ответа.") # Changed print to logger.error
            response = "" # Ensure response is an empty string
        except Exception as e:
            logger.error(f"AuthClient: Ошибка при чтении ответа от сервера аутентификации: {e}") # Changed print to logger.error
            response = "" # Ensure response is an empty string
        finally:
            writer.close()
            await writer.wait_closed()

        try:
            response_json = json.loads(response)
            status_from_auth_server = response_json.get("status")
            message_from_auth_server = response_json.get("message", "No message field in JSON response.")

            if status_from_auth_server == "success":
                status_to_return = "AUTH_SUCCESS" # Standardize status for AuthClient users
            elif status_from_auth_server == "failure":
                status_to_return = "AUTH_FAILURE"
            else: # Unknown status in JSON
                status_to_return = "AUTH_FAILURE"
                message_from_auth_server = f"Unknown status '{status_from_auth_server}' in auth server response. Full response: {response}"
            
            final_message = message_from_auth_server

        except json.JSONDecodeError:
            logger.error(f"AuthClient: JSONDecodeError when parsing auth server response: '{response}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "Invalid JSON response from auth server."
        except AttributeError: # If response_json is not a dict (e.g. json.loads returns a string/list)
            logger.error(f"AuthClient: AttributeError, response_json not a dict. Response: '{response}'")
            status_to_return = "AUTH_FAILURE"
            final_message = "Non-dictionary JSON response from auth server."

        # The session_token logic remains the same (currently always None from this method)
        session_token = None 
        # Example for future token extraction if auth_server provided it in JSON:
        if status_to_return == "AUTH_SUCCESS" and isinstance(response_json, dict):
           session_token = response_json.get("session_id") # Assuming auth_server returns session_id

        logger.debug(f"AuthClient._send_auth_command returning: status='{status_to_return}', message='{final_message}', token='{session_token}'")
        return status_to_return, final_message, session_token


    async def login_user(self, username, password):
        """
        Отправляет команду LOGIN на сервер аутентификации.
        Возвращает (bool, str, str|None): (успех, сообщение, session_token)
        """
        command_dict = {"action": "login", "username": username, "password": password}
        status, message, session_token = await self._send_auth_command(command_dict)
        
        authenticated = (status == "AUTH_SUCCESS")
        # Предположим, что сессионный токен - это имя пользователя при успехе (заглушка)
        # В реальном сценарии, токен должен приходить от сервера аутентификации
        if authenticated:
            # Это временная заглушка. Сервер аутентификации должен вернуть реальный токен.
            # Пока что используем username как псевдо-токен для демонстрационных целей.
            # session_token = username # Закомментировано, т.к. auth_server его не возвращает
            logger.debug(f"AuthClient.login_user returning: authenticated={authenticated}, message='{message}', token='{session_token}'")
            return True, message, session_token # session_token здесь будет None
        
        logger.debug(f"AuthClient.login_user returning: authenticated={authenticated}, message='{message}', token='{session_token}'")
        return False, message, None

    # async def register_user(self, username, password):
    #     """
    #     Отправляет команду REGISTER на сервер аутентификации.
    #     (Пока не используется активно в текущей логике гейм-сервера)
    #     Возвращает (bool, str): (успех, сообщение)
    #     """
    #     command = f"REGISTER {username} {password}"
    #     status, message, _ = await self._send_auth_command(command) # Токен не ожидается при регистрации
    #     return status == "REGISTER_SUCCESS", message # Предполагая такой статус от auth_server
    #
    # async def validate_token(self, token: str):
    #     """
    #     Отправляет команду VALIDATE_TOKEN на сервер аутентификации.
    #     (Пока не используется)
    #     Возвращает (bool, str): (валидность_токена, сообщение)
    #     """
    #     command = f"VALIDATE_TOKEN {token}"
    #     status, message, _ = await self._send_auth_command(command)
    #     return status == "TOKEN_VALID", message # Предполагая такой статус
    pass
