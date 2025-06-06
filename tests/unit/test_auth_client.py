import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import socket # для socket.timeout

from game_server.auth_client import AuthClient

@pytest.fixture
def auth_client():
    # Можно настроить хост и порт по умолчанию, если они не передаются в конструктор явно
    return AuthClient(auth_server_host="test_auth_host", auth_server_port=1234, timeout=0.1) # Short timeout for tests

@pytest.mark.asyncio
async def test_login_user_success(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    # Ожидаемый ответ от сервера аутентификации - используем "session_id" как ожидает клиент
    auth_response_data = {"status": "success", "message": "Successfully authenticated", "session_id": "testusertoken"}
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    mock_open_conn.assert_called_once_with("test_auth_host", 1234) # Используем позиционные аргументы

    expected_request_data = {"action": "login", "username": "testuser", "password": "password"}
    sent_data_bytes = mock_writer.write.call_args[0][0]
    assert json.loads(sent_data_bytes.decode('utf-8').strip()) == expected_request_data
    mock_writer.drain.assert_called_once()

    assert authenticated is True
    assert message == "Successfully authenticated"
    assert token == "testusertoken"

    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()


@pytest.mark.asyncio
async def test_login_user_failure_credentials(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"status": "failure", "message": "Invalid credentials"} # session_id не будет в этом случае
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "wrongpassword")

    assert authenticated is False
    assert message == "Invalid credentials"
    assert token is None # При AUTH_FAILURE токен None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_connection_refused(auth_client):
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=ConnectionRefusedError) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient
    assert message == f"AuthClient: Connection refused by authentication server at {auth_client.auth_host}:{auth_client.auth_port}."
    assert token is None

@pytest.mark.asyncio
async def test_login_user_timeout_on_connect(auth_client):
    # Тестируем asyncio.TimeoutError при вызове open_connection
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=asyncio.TimeoutError) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    assert message == f"AuthClient: Timeout when trying to connect to authentication server at {auth_client.auth_host}:{auth_client.auth_port} (timeout: {auth_client.timeout}s)."
    assert token is None

@pytest.mark.asyncio
async def test_login_user_timeout_on_read(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    mock_reader.readuntil.side_effect = asyncio.TimeoutError # Имитируем таймаут при чтении

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    assert message == f"AuthClient: Timeout during operation (drain or read) with authentication server {auth_client.auth_host}:{auth_client.auth_port} (timeout: {auth_client.timeout}s)."
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_oserror_on_connect(auth_client):
    # Тестируем OSError (например, socket.gaierror) при вызове open_connection
    test_os_error = OSError("Test Host not found")
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=test_os_error) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    assert message == f"AuthClient: Network error when connecting to authentication server at {auth_client.auth_host}:{auth_client.auth_port}: {test_os_error}"
    assert token is None

@pytest.mark.asyncio
async def test_login_user_json_decode_error(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    mock_reader.readuntil.return_value = b"not a valid json\n"

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    assert message == "Invalid JSON response from authentication server." # Сообщение из AuthClient
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_unexpected_response_format_missing_status(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"message": "Some data", "session_id": "atoken"} # Отсутствует "status"
    response_str = json.dumps(auth_response_data)
    mock_reader.readuntil.return_value = (response_str + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    # Сообщение из AuthClient
    expected_msg = f"Unknown status 'None' in authentication server response. Full response: {response_str}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_unexpected_response_format_missing_message(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False

    auth_response_data = {"status": "success", "session_id": "atoken"} # Отсутствует "message"
    mock_reader.readuntil.return_value = (json.dumps(auth_response_data) + '\n').encode('utf-8')

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is True # Статус "success" должен дать True
    assert message == "Message field is missing in JSON response." # Сообщение из AuthClient
    assert token == "atoken" # Токен должен быть извлечен
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_generic_exception_on_connect(auth_client):
    test_exception = Exception("Generic connect error")
    with patch('asyncio.open_connection', new_callable=AsyncMock, side_effect=test_exception) as mock_open_conn:
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    expected_msg = f"AuthClient: Unexpected error when connecting to authentication server at {auth_client.auth_host}:{auth_client.auth_port}: {test_exception}"
    assert message == expected_msg
    assert token is None

@pytest.mark.asyncio
async def test_login_user_generic_exception_on_read(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    test_exception = Exception("Generic read error")
    mock_reader.readuntil.side_effect = test_exception

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    expected_msg = f"AuthClient: Unexpected error during communication with {auth_client.auth_host}:{auth_client.auth_port}: {test_exception}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_login_user_incomplete_read_error(auth_client):
    mock_reader = AsyncMock(spec=asyncio.StreamReader)
    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False
    partial_data = b"some partial data"
    incomplete_read_error = asyncio.IncompleteReadError(partial_data, None)
    mock_reader.readuntil.side_effect = incomplete_read_error

    with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(mock_reader, mock_writer)):
        authenticated, message, token = await auth_client.login_user("testuser", "password")

    assert authenticated is False
    expected_msg = f"AuthClient: Authentication server {auth_client.auth_host}:{auth_client.auth_port} closed connection prematurely. Partial data: {partial_data!r}"
    assert message == expected_msg
    assert token is None
    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_called_once()
