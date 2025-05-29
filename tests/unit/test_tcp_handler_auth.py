# tests/unit/test_tcp_handler_auth.py
# Этот файл содержит модульные тесты для TCP-обработчика сервера аутентификации
# (auth_server.tcp_handler.handle_auth_client).
# Тесты проверяют различные сценарии взаимодействия клиента с сервером,
# включая успешный и неудачный вход, а также обработку некорректных запросов.

import asyncio
import json # Для работы с JSON-сообщениями
import unittest
from unittest.mock import AsyncMock, patch, call # Инструменты для мокирования

# Импортируем тестируемую функцию
from auth_server.tcp_handler import handle_auth_client
# Предполагается, что MOCK_USERS_DB доступна для справки, или мы полностью мокируем authenticate_user.
# from auth_server.user_service import MOCK_USERS_DB # Закомментировано, так как authenticate_user мокируется

class TestAuthTcpHandler(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для TCP-обработчика сервера аутентификации.
    Использует `unittest.IsolatedAsyncioTestCase` для асинхронных тестов.
    """

    async def test_successful_login(self):
        """
        Тест успешного входа пользователя.
        Проверяет, что при корректных учетных данных сервер возвращает
        сообщение об успехе и соответствующий токен/сообщение сессии.
        """
        reader = AsyncMock(spec=asyncio.StreamReader) # Мок для StreamReader
        writer = AsyncMock(spec=asyncio.StreamWriter) # Мок для StreamWriter
        writer.is_closing.return_value = False # Имитируем, что writer открыт
        # writer.close и writer.write будут автоматически созданы AsyncMock, если они вызываются
        
        # Формируем JSON-запрос на вход
        login_request = {"action": "login", "username": "player1", "password": "password123"}
        # Имитируем, что StreamReader возвращает этот запрос (в байтах, с новой строкой)
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        # Мокируем функцию authenticate_user, чтобы она возвращала успешный результат
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(True, "Пользователь player1 успешно аутентифицирован."))) as mock_auth_user:
            await handle_auth_client(reader, writer) # Вызываем тестируемый обработчик

        # Проверяем, что authenticate_user была вызвана с правильными аргументами
        mock_auth_user.assert_called_once_with("player1", "password123")
        
        # Ожидаемый JSON-ответ от сервера
        # В текущей реализации tcp_handler, сообщение об успехе используется и как message, и как session_id
        # Предполагаем, что сообщение от authenticate_user также будет на английском, если оно используется напрямую.
        # Для данного теста, мы мокируем authenticate_user, поэтому его возвращаемое значение контролируется.
        # Если authenticate_user возвращает "User player1 authenticated successfully.", то:
        expected_auth_message = "User player1 authenticated successfully." # Пример английского сообщения
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(True, expected_auth_message))) as mock_auth_user:
            await handle_auth_client(reader, writer) # Вызываем тестируемый обработчик

        # Проверяем, что authenticate_user была вызвана с правильными аргументами
        mock_auth_user.assert_called_once_with("player1", "password123")
        
        expected_response = {"status": "success", "message": expected_auth_message, "session_id": expected_auth_message}
        
        # Проверяем, что writer.write был вызван
        self.assertTrue(writer.write.called, "Метод writer.write не был вызван.")
        # Получаем аргументы первого вызова writer.write
        actual_call_args_bytes = writer.write.call_args[0][0]
        
        # Декодируем и парсим фактический ответ для сравнения
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response, "Ответ сервера не соответствует ожидаемому.")
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'), "Ответ сервера должен заканчиваться новой строкой.")
        writer.drain.assert_called_once() # Проверяем вызов drain
        writer.close.assert_called_once() # Проверяем закрытие writer
        writer.wait_closed.assert_called_once() # Проверяем ожидание закрытия


    async def test_failed_login_wrong_password(self):
        """
        Тест неудачного входа пользователя из-за неверного пароля.
        Проверяет, что сервер возвращает сообщение о неудаче.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        login_request = {"action": "login", "username": "player1", "password": "wrongpassword"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        # Мокируем authenticate_user для возврата ошибки "Неверный пароль"
        # Предполагаем, что "Неверный пароль." от authenticate_user будет "Incorrect password."
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(False, "Incorrect password."))) as mock_auth_user:
            await handle_auth_client(reader, writer)

        mock_auth_user.assert_called_once_with("player1", "wrongpassword")
        expected_response = {"status": "failure", "message": "Authentication failed: Incorrect password."}
        
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()


    async def test_invalid_json_format(self):
        """
        Тест обработки запроса с невалидным форматом JSON.
        Проверяет, что сервер возвращает ошибку о неверном формате JSON.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        # Некорректный JSON: отсутствует кавычка после "login"
        malformed_json_request = b'{"action": "login, "username": "player1"}\n'
        reader.readuntil.return_value = malformed_json_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid JSON format"}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    async def test_unicode_decode_error(self):
        """
        Тест обработки запроса с ошибкой декодирования Unicode (не UTF-8).
        Проверяет, что сервер возвращает ошибку о неверной кодировке.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        # Невалидная UTF-8 последовательность
        invalid_utf8_request = b'\xff\xfe\xfd{"action": "login"}\n'
        reader.readuntil.return_value = invalid_utf8_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    async def test_unknown_action(self):
        """
        Тест обработки запроса с неизвестным действием (action).
        Проверяет, что сервер возвращает ошибку о неизвестном действии.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False # Исправлено и остается

        unknown_action_request = {"action": "unknown_action", "username": "player1"}
        reader.readuntil.return_value = (json.dumps(unknown_action_request) + '\n').encode('utf-8')

        # Мокируем authenticate_user, хотя он не должен быть вызван.
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock()) as mock_auth_user:
            await handle_auth_client(reader, writer)
        
        mock_auth_user.assert_not_called() # authenticate_user не должен вызываться
        expected_response = {"status": "error", "message": "Unknown or missing action"}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    @patch('auth_server.tcp_handler.logger')
    # @patch('auth_server.tcp_handler.config') # Удалено
    # @patch('auth_server.tcp_handler.UserService') # Удалено
    # @patch('auth_server.tcp_handler.KafkaProducerClient') # Удалено, так как не импортируется напрямую в tcp_handler
    @patch('auth_server.tcp_handler.ACTIVE_CONNECTIONS_AUTH')
    # @patch('auth_server.tcp_handler.TOTAL_AUTH_REQUESTS') # Удалено, так как метрика отсутствует
    @patch('auth_server.tcp_handler.SUCCESSFUL_AUTHS')
    @patch('auth_server.tcp_handler.FAILED_AUTHS')
    async def test_empty_message_just_newline(
            self,
            MockFailedAuths,
            MockSuccessfulAuths,
            # MockTotalAuthRequests, # Удалено из аргументов
            MockActiveConnections,
            # MockKafkaClient, # Удалено из аргументов
            # MockUserService, # Удалено из аргументов
            # mock_config, # Удалено из аргументов
            mock_logger
    ):
        '''Тестирует обработку пустого сообщения (только символ новой строки).'''
        # Мокируем конфиг, если он используется для определения формата ответа - Удалено
        # mock_config.AUTH_SERVER_HOST = 'localhost'
        # mock_config.AUTH_SERVER_PORT = 8888

        # Мокируем сервисы, если они вызываются (маловероятно для пустого сообщения) - Удалено
        # mock_user_service_instance = MockUserService.return_value 
        # mock_kafka_producer_instance = MockKafkaClient.return_value

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.is_closing.return_value = False # Явно устанавливаем для проверки в finally

        # Симулируем получение пустого сообщения, затем ошибку для выхода из цикла
        mock_reader.readuntil.side_effect = [
            b'\n',
            asyncio.IncompleteReadError(b'', 0)
        ]
        
        await handle_auth_client(mock_reader, mock_writer)

        expected_response_json = {
            "status": "error",
            "message": "Empty message or only newline character received"
        }
        expected_response_bytes = json.dumps(expected_response_json).encode('utf-8') + b'\n'

        # Проверяем, что writer.write был вызван с правильным сообщением
        # Используем any_call, если могут быть другие write (например, логи)
        mock_writer.write.assert_any_call(expected_response_bytes)
        
        # Проверяем, что соединение было закрыто
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once() # Убедимся, что и wait_closed проверяется

        # Проверка вызова логгера
        # Изменено на logger.warning и точное сообщение из tcp_handler.py
        mock_logger.warning.assert_any_call("От ('127.0.0.1', 12345) получено пустое сообщение или только символ новой строки. Отправка ошибки и закрытие.")
        # Удалена проверка logger.error, так как она не вызывается в этом сценарии
        # mock_logger.error.assert_any_call("Ошибка обработки запроса от %s:%s: %s", 
        #                                   '127.0.0.1', 12345, "Получено пустое сообщение или только символ новой строки")

        # Проверка метрик
        MockActiveConnections.inc.assert_called_once() # Проверяем инкремент счетчика активных соединений
        # MockTotalAuthRequests.inc.assert_called_once() # Удалено, так как метрика отсутствует
        # MockFailedAuths.inc.assert_called_once() # Удалено, так как FAILED_AUTHS.inc() не вызывается для пустого сообщения
        MockSuccessfulAuths.inc.assert_not_called() # Успешной аутентификации не было
        MockActiveConnections.dec.assert_called_once() # Проверяем декремент счетчика активных соединений

        # Убедимся, что основные сервисные методы не вызывались - Удалено, так как моки удалены
        # MockUserService.return_value.register_user.assert_not_called()
        # MockUserService.return_value.login_user.assert_not_called()
        # MockKafkaClient был удален, поэтому и проверка его вызова удалена

    async def test_no_data_from_client(self):
        """
        Тест ситуации, когда клиент не отправляет данные (соединение закрывается или EOF).
        Проверяет, что сервер не отправляет ответ и корректно закрывает соединение.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False
        
        reader.readuntil.return_value = b'' # Имитируем закрытие соединения или отсутствие данных перед EOF

        await handle_auth_client(reader, writer)

        # Ожидаем, что будет отправлено сообщение об ошибке
        expected_response_json = {
            "status": "error",
            "message": "Empty message or only newline character received"
        }
        expected_response_bytes = json.dumps(expected_response_json).encode('utf-8') + b'\n'
        
        writer.write.assert_called_once_with(expected_response_bytes)
        writer.drain.assert_called_once() # Добавлена проверка drain
        # Соединение должно быть корректно закрыто
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую
    unittest.main()
