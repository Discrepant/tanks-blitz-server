import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Добавляем путь к корневой директории проекта, чтобы можно было импортировать auth_server
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth_server.user_service import authenticate_user, MOCK_USERS_DB
from auth_server.tcp_handler import handle_auth_client
from auth_server.main import main as auth_server_main # Импортируем main для возможного запуска сервера в тестах

# Убедимся, что MOCK_USERS_DB содержит тестовых пользователей
if "testuser_auth" not in MOCK_USERS_DB:
    MOCK_USERS_DB["testuser_auth"] = "testpass_auth"
if "testuser_auth_wrong" not in MOCK_USERS_DB:
    MOCK_USERS_DB["testuser_auth_wrong"] = "correct_password"


class TestAuthUserService(unittest.IsolatedAsyncioTestCase):

    async def test_authenticate_user_success(self):
        authenticated, message = await authenticate_user("testuser_auth", "testpass_auth")
        self.assertTrue(authenticated)
        self.assertIn("успешно аутентифицирован", message)

    async def test_authenticate_user_wrong_password(self):
        authenticated, message = await authenticate_user("testuser_auth_wrong", "wrong_password")
        self.assertFalse(authenticated)
        self.assertEqual("Неверный пароль.", message)

    async def test_authenticate_user_not_found(self):
        authenticated, message = await authenticate_user("nonexistentuser", "somepassword")
        self.assertFalse(authenticated)
        self.assertEqual("Пользователь не найден.", message)

class TestAuthTcpHandler(unittest.IsolatedAsyncioTestCase):

    async def test_handle_auth_client_login_success(self):
        reader = asyncio.StreamReader()
        # Кодируем с переводом строки, как это делает клиент
        reader.feed_data(b"LOGIN testuser_auth testpass_auth\n")
        reader.feed_eof() # Сигнализируем конец данных

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        # Мокаем drain и close как асинхронные функции
        writer.drain = MagicMock(return_value=asyncio.Future())
        writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future())
        writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()


        with patch('auth_server.tcp_handler.authenticate_user',
                   return_value=(True, "Успех")) as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_called_once_with("testuser_auth", "testpass_auth")
        # Проверяем, что writer.write был вызван с правильным сообщением
        # Ожидаем байты, так как write принимает байты
        # Также ожидаем перевод строки в конце сообщения от сервера
        writer.write.assert_called_with(b"AUTH_SUCCESS Успех\n")
        writer.close.assert_called_once()

    async def test_handle_auth_client_login_failure(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"LOGIN testuser_auth wrongpass\n")
        reader.feed_eof()

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        writer.drain = MagicMock(return_value=asyncio.Future())
        writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future())
        writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()

        with patch('auth_server.tcp_handler.authenticate_user',
                   return_value=(False, "Неверный пароль")) as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_called_once_with("testuser_auth", "wrongpass")
        writer.write.assert_called_with(b"AUTH_FAILURE Неверный пароль\n")
        writer.close.assert_called_once()

    async def test_handle_auth_client_invalid_command(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"INVALIDCMD user pass\n") # Неверная команда
        reader.feed_eof()

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        writer.drain = MagicMock(return_value=asyncio.Future())
        writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future())
        writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()

        # authenticate_user не должен быть вызван
        with patch('auth_server.tcp_handler.authenticate_user') as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_not_called()
        writer.write.assert_called_with(b"INVALID_COMMAND Формат: LOGIN username password\n")
        writer.close.assert_called_once()

# Для запуска тестов, если файл выполняется напрямую
if __name__ == '__main__':
    unittest.main()
