# tests/test_auth_server.py
# Этот файл содержит модульные тесты для сервера аутентификации.
# Он проверяет как сервис аутентификации пользователей (user_service),
# так и обработчик TCP-соединений (tcp_handler).
# Примечание: Эти тесты могут быть устаревшими или дублировать тесты из папки tests/unit/.
# Рекомендуется проверить и, возможно, объединить их с более новыми тестами.

import asyncio
import unittest
from unittest.mock import patch, MagicMock # Инструменты для мокирования

# Добавляем путь к корневой директории проекта, чтобы можно было импортировать auth_server.
# Это стандартная практика для запуска тестов, находящихся в поддиректориях.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from auth_server.user_service import authenticate_user, MOCK_USERS_DB # Функции и данные для аутентификации
from auth_server.tcp_handler import handle_auth_client # Обработчик TCP-запросов
from auth_server.main import main as auth_server_main # Главная функция сервера (для возможных интеграционных тестов)

# Убедимся, что MOCK_USERS_DB содержит необходимых тестовых пользователей.
# Это гарантирует, что тесты будут работать независимо от исходного состояния MOCK_USERS_DB.
if "testuser_auth" not in MOCK_USERS_DB:
    MOCK_USERS_DB["testuser_auth"] = "testpass_auth"
if "testuser_auth_wrong" not in MOCK_USERS_DB:
    MOCK_USERS_DB["testuser_auth_wrong"] = "correct_password"


class TestAuthUserService(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для проверки сервиса аутентификации пользователей (`auth_server.user_service`).
    Использует `unittest.IsolatedAsyncioTestCase` для асинхронных тестов.
    """

    async def test_authenticate_user_success(self):
        """
        Тест успешной аутентификации пользователя.
        Проверяет, что `authenticate_user` возвращает True и корректное сообщение.
        """
        authenticated, message = await authenticate_user("testuser_auth", "testpass_auth")
        self.assertTrue(authenticated, "Аутентификация должна быть успешной с верными данными.")
        self.assertIn("успешно аутентифицирован", message, "Сообщение должно подтверждать успешную аутентификацию.")

    async def test_authenticate_user_wrong_password(self):
        """
        Тест аутентификации пользователя с неверным паролем.
        Проверяет, что `authenticate_user` возвращает False и сообщение о неверном пароле.
        """
        authenticated, message = await authenticate_user("testuser_auth_wrong", "wrong_password")
        self.assertFalse(authenticated, "Аутентификация должна провалиться с неверным паролем.")
        self.assertEqual("Неверный пароль.", message, "Сообщение должно указывать на неверный пароль.")

    async def test_authenticate_user_not_found(self):
        """
        Тест аутентификации несуществующего пользователя.
        Проверяет, что `authenticate_user` возвращает False и сообщение о том, что пользователь не найден.
        """
        authenticated, message = await authenticate_user("nonexistentuser", "somepassword")
        self.assertFalse(authenticated, "Аутентификация должна провалиться для несуществующего пользователя.")
        self.assertEqual("Пользователь не найден.", message, "Сообщение должно указывать, что пользователь не найден.")

class TestAuthTcpHandler(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для проверки TCP-обработчика сервера аутентификации (`auth_server.tcp_handler`).
    Тестирует логику обработки входящих TCP-сообщений.
    """

    async def test_handle_auth_client_login_success(self):
        """
        Тест успешного логина через TCP-обработчик.
        Имитирует входящее TCP-соединение с корректными данными для входа.
        Проверяет, что вызывается `authenticate_user` и клиенту отправляется верный ответ.
        """
        reader = asyncio.StreamReader()
        # Кодируем сообщение с символом новой строки, как это делает реальный клиент.
        # Сервер ожидает JSON, поэтому отправляем JSON-строку.
        login_payload = {"action": "login", "username": "testuser_auth", "password": "testpass_auth"}
        reader.feed_data( (f"{json.dumps(login_payload)}\n").encode('utf-8') )
        reader.feed_eof() # Сигнализируем конец данных (EOF)

        writer = MagicMock(spec=asyncio.StreamWriter) # Мок для StreamWriter
        writer.get_extra_info.return_value = ('127.0.0.1', 12345) # Имитируем адрес клиента
        # Мокируем асинхронные методы drain и close, чтобы они возвращали завершенный Future.
        writer.drain = MagicMock(return_value=asyncio.Future())
        writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future())
        writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock() # Мок для метода write

        # Мокируем `authenticate_user` внутри `tcp_handler`, чтобы изолировать тест.
        # Ожидаем, что `handle_auth_client` вызовет его с правильными аргументами.
        # Сервер `auth_server` теперь возвращает JSON, поэтому ожидаемый ответ от `authenticate_user`
        # должен соответствовать тому, что `handle_auth_client` ожидает для формирования JSON ответа.
        # Предположим, что `authenticate_user` возвращает (True, "Успешный вход", "fake_session_id_123")
        # Но `handle_auth_client` формирует свой JSON, поэтому мы мокируем то, что возвращает `authenticate_user`
        # на более низком уровне.
        # В данном случае, tcp_handler ожидает от user_service (True/False, сообщение_или_токен)
        # и затем формирует JSON.
        # Если authenticate_user возвращает (True, "токен_сессии_или_сообщение_успеха"), то handle_auth_client
        # формирует JSON: {"status": "success", "message": "токен_сессии_или_сообщение_успеха", "session_id": "токен_сессии_или_сообщение_успеха"}
        
        # Обновляем мок authenticate_user, чтобы он соответствовал ожиданиям JSON-обработчика
        # Теперь authenticate_user возвращает (bool, message_or_token)
        # А tcp_handler.py формирует JSON {"status": "success/failure", "message": message, "session_id": token_if_success}
        with patch('auth_server.tcp_handler.authenticate_user', return_value=(True, "fake_token_123")) as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_called_once_with("testuser_auth", "testpass_auth")
        
        # Проверяем, что writer.write был вызван с правильным JSON-сообщением.
        # Ожидаем байты, так как `writer.write` принимает байты.
        # Также ожидаем символ новой строки в конце сообщения от сервера.
        expected_response_dict = {"status": "success", "message": "fake_token_123", "session_id": "fake_token_123"}
        expected_response_bytes = (json.dumps(expected_response_dict) + "\n").encode('utf-8')
        writer.write.assert_called_with(expected_response_bytes)
        writer.close.assert_called_once() # Проверяем, что соединение было закрыто

    async def test_handle_auth_client_login_failure(self):
        """
        Тест неудачного логина через TCP-обработчик.
        Имитирует входящее TCP-соединение с неверными данными для входа.
        """
        reader = asyncio.StreamReader()
        login_payload = {"action": "login", "username": "testuser_auth", "password": "wrongpass"}
        reader.feed_data( (f"{json.dumps(login_payload)}\n").encode('utf-8') )
        reader.feed_eof()

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        writer.drain = MagicMock(return_value=asyncio.Future()); writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future()); writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()

        with patch('auth_server.tcp_handler.authenticate_user', return_value=(False, "Неверный пароль")) as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_called_once_with("testuser_auth", "wrongpass")
        expected_response_dict = {"status": "failure", "message": "Аутентификация не удалась: Неверный пароль"}
        expected_response_bytes = (json.dumps(expected_response_dict) + "\n").encode('utf-8')
        writer.write.assert_called_with(expected_response_bytes)
        writer.close.assert_called_once()

    async def test_handle_auth_client_invalid_json_command(self):
        """
        Тест обработки невалидной JSON-команды.
        Имитирует отправку строки, которая не является корректным JSON.
        """
        reader = asyncio.StreamReader()
        reader.feed_data(b"ЭтоНеJSON\n") # Невалидная JSON-команда
        reader.feed_eof()

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        writer.drain = MagicMock(return_value=asyncio.Future()); writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future()); writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()

        # `authenticate_user` не должен быть вызван, так как парсинг JSON провалится раньше.
        with patch('auth_server.tcp_handler.authenticate_user') as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_not_called() # `authenticate_user` не должен вызываться
        # Ожидаем ответ об ошибке JSON
        expected_response_dict = {"status": "error", "message": "Невалидный формат JSON"}
        expected_response_bytes = (json.dumps(expected_response_dict) + "\n").encode('utf-8')
        writer.write.assert_called_with(expected_response_bytes)
        writer.close.assert_called_once()

    async def test_handle_auth_client_unknown_action(self):
        """
        Тест обработки JSON-команды с неизвестным действием (action).
        """
        reader = asyncio.StreamReader()
        payload = {"action": "UNKNOWN_ACTION", "username": "user", "password": "pw"}
        reader.feed_data( (f"{json.dumps(payload)}\n").encode('utf-8') )
        reader.feed_eof()

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        writer.drain = MagicMock(return_value=asyncio.Future()); writer.drain.return_value.set_result(None)
        writer.close = MagicMock()
        writer.wait_closed = MagicMock(return_value=asyncio.Future()); writer.wait_closed.return_value.set_result(None)
        writer.write = MagicMock()
        
        with patch('auth_server.tcp_handler.authenticate_user') as mock_auth:
            await handle_auth_client(reader, writer)

        mock_auth.assert_not_called() # `authenticate_user` не должен вызываться для неизвестного действия
        expected_response_dict = {"status": "error", "message": "Неизвестное или отсутствующее действие"}
        expected_response_bytes = (json.dumps(expected_response_dict) + "\n").encode('utf-8')
        writer.write.assert_called_with(expected_response_bytes)
        writer.close.assert_called_once()

# Блок для запуска тестов, если этот файл выполняется напрямую.
if __name__ == '__main__':
    # Это позволяет запускать тесты командой: python tests/test_auth_server.py
    unittest.main()
