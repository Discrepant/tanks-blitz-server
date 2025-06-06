import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import socket # для socket.timeout

from game_server.auth_client import AuthClient

@pytest.fixture
def auth_client():
    # Можно настроить хост и порт по умолчанию, если они не передаются в конструктор явно
    return AuthClient(auth_server_host="test_auth_host", auth_server_port=1234, timeout=0.1) # Короткий таймаут для тестов

@pytest.mark.asyncio
async def test_login_user_success(auth_client): # Тест успешного входа пользователя
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    # Ожидаемый ответ от сервера аутентификации - используем "session_id", как ожидает клиент
    auth_response_data = {"status": "success", "message": "Успешная аутентификация", "session_id": "testusertoken"} # Сообщение на русском
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    mock_open_conn.assert_called_once_with("test_auth_host", 1234) # Используем позиционные аргументы

    expected_request_data = {"action": "login", "username": "testuser", "password": "password"}
    sent_data_bytes = mock_writer.write.call_args[0][0]
    assert json.loads(sent_data_bytes.decode('utf-8').strip()) == expected_request_data
    mock_writer.drain.assert_called_once()

    assert authenticated is True
    assert message == "Успешная аутентификация" # Проверяем русское сообщение
    assert token == "testusertoken"

    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_login_user_failure_credentials(auth_client): # Тест неудачного входа пользователя (неверные учетные данные)
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"status": "failure", "message": "Неверные учетные данные"} # session_id не будет в этом случае. Сообщение на русском.
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "wrongpassword")

    assert authenticated is False
    assert message == "Неверные учетные данные" # Проверяем русское сообщение
    assert token is None # При AUTH_FAILURE токен None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_connection_refused(auth_client): # Тест отказа в соединении при входе пользователя
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=ConnectionRefusedError) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    assert message == f"AuthClient: Сервер аутентификации по адресу {auth_client.auth_host}:{auth_client.auth_port} отказал в соединении."
    assert token is None

@pytest.mark.asyncio
async def test_login_user_timeout_on_connect(auth_client): # Тест таймаута при подключении во время входа пользователя
    # Тестируем asyncio.TimeoutError при вызове open_connection
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=asyncio.TimeoutError) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    assert message == f"AuthClient: Таймаут при попытке подключения к серверу аутентификации по адресу {auth_client.auth_host}:{auth_client.auth_port} (таймаут: {auth_client.timeout}с)."
    assert token is None

@pytest.mark.asyncio
async def test_login_user_timeout_on_read(auth_client): # Тест таймаута при чтении ответа во время входа пользователя
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    mock_reader.readuntil.side_effect = asyncio.TimeoutError # Имитируем таймаут при чтении

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    assert message == f"AuthClient: Таймаут во время операции (drain или read) с сервером аутентификации {auth_client.auth_host}:{auth_client.auth_port} (таймаут: {auth_client.timeout}с)."
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_oserror_on_connect(auth_client): # Тест OSError при подключении во время входа пользователя
    # Тестируем OSError (например, socket.gaierror) при вызове open_connection
    test_os_error = OSError("Test Host not found")
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=test_os_error) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    assert message == f"AuthClient: Сетевая ошибка при подключении к серверу аутентификации по адресу {auth_client.auth_host}:{auth_client.auth_port}: {test_os_error}"
    assert token is None

@pytest.mark.asyncio
async def test_login_user_json_decode_error(auth_client): # Тест ошибки декодирования JSON при входе пользователя
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    mock_reader.readuntil.return_value = b"not a valid json\n"

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    assert message == "Неверный JSON-ответ от сервера аутентификации." # Сообщение из AuthClient (переведено)
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_unexpected_response_format_missing_status(auth_client): # Тест неожиданного формата ответа (отсутствует статус)
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"message": "Some data", "session_id": "atoken"} # Отсутствует "status"
    response_str = json.dumps(auth_response_data)
    mock_reader.readuntil.return_value = (response_str + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (переведено)
    expected_msg = f"Неизвестный статус 'None' в ответе сервера аутентификации. Полный ответ: {response_str}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_unexpected_response_format_missing_message(auth_client): # Тест неожиданного формата ответа (отсутствует сообщение)
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"status": "success", "session_id": "atoken"} # Отсутствует "message"
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is True # Статус "success" должен дать True
    assert message == "Поле 'message' отсутствует в JSON-ответе." # Сообщение из AuthClient (переведено)
    assert token == "atoken" # Токен должен быть извлечен
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_generic_exception_on_connect(auth_client): # Тест общей ошибки при подключении
    test_exception = Exception("Generic connect error")
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=test_exception) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    expected_msg = f"AuthClient: Неожиданная ошибка при подключении к серверу аутентификации по адресу {auth_client.auth_host}:{auth_client.auth_port}: {test_exception}"
    assert message == expected_msg
    assert token is None

@pytest.mark.asyncio
async def test_login_user_generic_exception_on_read(auth_client): # Тест общей ошибки при чтении
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    test_exception = Exception("Generic read error")
    mock_reader.readuntil.side_effect = test_exception

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    expected_msg = f"AuthClient: Неожиданная ошибка во время обмена данными с {auth_client.auth_host}:{auth_client.auth_port}: {test_exception}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_incomplete_read_error(auth_client): # Тест ошибки неполного чтения
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    partial_data = b"some partial data"
    incomplete_read_error = asyncio.IncompleteReadError(partial_data, None)
    mock_reader.readuntil.side_effect = incomplete_read_error

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient (должно быть переведено в AuthClient)
    expected_msg = f"AuthClient: Сервер аутентификации {auth_client.auth_host}:{auth_client.auth_port} преждевременно закрыл соединение. Частичные данные: {partial_data!r}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()
