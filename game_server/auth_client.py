import asyncio
import json # Added import

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
            print(f"Ответ от сервера аутентификации: {response}")
        except asyncio.TimeoutError:
            response = "AUTH_FAILURE Ответ от сервера аутентификации не получен (таймаут)."
            print(response)
        except asyncio.IncompleteReadError:
            response = "AUTH_FAILURE Сервер аутентификации закрыл соединение без полного ответа."
            print(response)
        except Exception as e:
            response = f"AUTH_FAILURE Ошибка при чтении ответа от сервера аутентификации: {e}"
            print(response)
        finally:
            writer.close()
            await writer.wait_closed()

        parts = response.split(" ", 1)
        status = parts[0]
        message = parts[1] if len(parts) > 1 else "Нет дополнительного сообщения."

        # Предполагаем, что токен может быть частью сообщения при успехе
        # Это очень упрощенная логика для токена!
        session_token = None
        if status == "AUTH_SUCCESS":
            # Пример: "AUTH_SUCCESS Пользователь player1 успешно аутентифицирован. Token: блаблабла"
            # В user_service.py пока нет генерации токена, это задел на будущее.
            # Сейчас просто используем имя пользователя как заглушку для токена, если он успешен.
            # В реальном приложении сервер аутентификации должен был бы вернуть токен.
            # Мы здесь его не генерируем, а ожидаем от auth_server.
            # Так как auth_server его не шлет, токен будет None.
            # Для демонстрации можно было бы сделать так:
            # if "Token: " in message: session_token = message.split("Token: ")[1]
            # Но пока что оставим None, т.к. auth_server не возвращает токен
            pass # session_token остается None

        return status, message, session_token


    async def login_user(self, username, password):
        """
        Отправляет команду LOGIN на сервер аутентификации.
        Возвращает (bool, str, str|None): (успех, сообщение, session_token)
        """
        command_dict = {"action": "login", "username": username, "password": password}
        status, message, session_token = await self._send_auth_command(command_dict)
        # Предположим, что сессионный токен - это имя пользователя при успехе (заглушка)
        # В реальном сценарии, токен должен приходить от сервера аутентификации
        if status == "AUTH_SUCCESS":
            # Это временная заглушка. Сервер аутентификации должен вернуть реальный токен.
            # Пока что используем username как псевдо-токен для демонстрационных целей.
            # session_token = username # Закомментировано, т.к. auth_server его не возвращает
            return True, message, session_token # session_token здесь будет None
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
