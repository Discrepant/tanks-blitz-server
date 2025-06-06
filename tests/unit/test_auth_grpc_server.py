import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import grpc
from grpc.aio import insecure_channel, server as grpc_aio_server

# Предполагается, что auth_service_pb2 и auth_service_pb2_grpc доступны в PYTHONPATH
# или через относительные импорты, если grpc_generated является частью пакета
from auth_server.grpc_generated import auth_service_pb2
from auth_server.grpc_generated import auth_service_pb2_grpc
from auth_server.auth_grpc_server import AuthServiceServicer
from auth_server.user_service import UserService # Для мокирования

# Фикстура для создания мок-экземпляра UserService
@pytest.fixture
def mock_user_service():
    service = MagicMock(spec=UserService)
    # Методы должны быть AsyncMock, так как они вызываются с await
    service.authenticate_user = AsyncMock()
    service.create_user = AsyncMock()
    return service

# Фикстура для запуска тестового gRPC сервера
@pytest.fixture
async def test_grpc_server(mock_user_service):
    test_server = grpc_aio_server()
    auth_service_pb2_grpc.add_AuthServiceServicer_to_server(
        AuthServiceServicer(user_svc_instance=mock_user_service), test_server # Исправлено имя аргумента
    )
    port = test_server.add_insecure_port('[::]:0') # Используем порт 0 для автоматического выбора свободного порта

    await test_server.start()
    yield f'localhost:{port}', test_server # Возвращаем адрес и сам сервер

    await test_server.stop(None)

# Тесты для AuthenticateUser
@pytest.mark.asyncio
async def test_authenticate_user_success(test_grpc_server, mock_user_service):
    server_address, _ = test_grpc_server
    mock_user_service.authenticate_user.return_value = (True, "Authentication successful")

    async with insecure_channel(server_address) as channel:
        stub = auth_service_pb2_grpc.AuthServiceStub(channel)
        request = auth_service_pb2.AuthRequest(username="testuser", password="password")
        response = await stub.AuthenticateUser(request)

    mock_user_service.authenticate_user.assert_called_once_with("testuser", "password")
    assert response.authenticated is True
    assert response.message == "Authentication successful"
    assert response.token == "testuser" # Токен - это имя пользователя при успехе

@pytest.mark.asyncio
async def test_authenticate_user_failure(test_grpc_server, mock_user_service):
    server_address, _ = test_grpc_server
    mock_user_service.authenticate_user.return_value = (False, "Invalid credentials")

    async with insecure_channel(server_address) as channel:
        stub = auth_service_pb2_grpc.AuthServiceStub(channel)
        request = auth_service_pb2.AuthRequest(username="testuser", password="wrongpassword")
        response = await stub.AuthenticateUser(request)

    mock_user_service.authenticate_user.assert_called_once_with("testuser", "wrongpassword")
    assert response.authenticated is False
    assert response.message == "Invalid credentials"
    assert response.token == ""

# Тесты для RegisterUser
@pytest.mark.asyncio
async def test_register_user_success(test_grpc_server, mock_user_service):
    server_address, _ = test_grpc_server
    mock_user_service.create_user.return_value = (True, "User registered successfully")

    # Мокируем объект pbkdf2_sha256 в модуле auth_grpc_server
    with patch('auth_server.auth_grpc_server.pbkdf2_sha256') as mock_pbkdf2_object:
        # Настраиваем метод hash на мок-объекте pbkdf2_sha256
        mock_pbkdf2_object.hash.return_value = "hashed_password_value"

        async with insecure_channel(server_address) as channel:
            stub = auth_service_pb2_grpc.AuthServiceStub(channel)
            request = auth_service_pb2.AuthRequest(username="newuser", password="newpassword")
            response = await stub.RegisterUser(request)

    mock_pbkdf2_object.hash.assert_called_once_with("newpassword") # Проверяем вызов на мок-методе hash
    mock_user_service.create_user.assert_called_once_with("newuser", "hashed_password_value")
    assert response.authenticated is False # По логике RegisterUser, authenticated всегда False в ответе
    assert response.message == "Registration successful. Please login." # Сообщение кастомизируется
    assert response.token == ""

@pytest.mark.asyncio
async def test_register_user_failure_user_exists(test_grpc_server, mock_user_service):
    server_address, _ = test_grpc_server
    mock_user_service.create_user.return_value = (False, "User already exists")

    with patch('auth_server.auth_grpc_server.pbkdf2_sha256') as mock_pbkdf2_object:
        mock_pbkdf2_object.hash.return_value = "hashed_password_value"

        async with insecure_channel(server_address) as channel:
            stub = auth_service_pb2_grpc.AuthServiceStub(channel)
            request = auth_service_pb2.AuthRequest(username="existinguser", password="password")
            response = await stub.RegisterUser(request)

    mock_pbkdf2_object.hash.assert_called_once_with("password")
    mock_user_service.create_user.assert_called_once_with("existinguser", "hashed_password_value")
    assert response.authenticated is False
    assert response.message == "Registration failed: User already exists" # Сообщение кастомизируется
    assert response.token == ""

@pytest.mark.asyncio
async def test_register_user_hash_exception(test_grpc_server, mock_user_service):
    server_address, _ = test_grpc_server

    with patch('auth_server.auth_grpc_server.pbkdf2_sha256') as mock_pbkdf2_object:
        mock_pbkdf2_object.hash.side_effect = Exception("Hashing error")

        async with insecure_channel(server_address) as channel:
            stub = auth_service_pb2_grpc.AuthServiceStub(channel)
            request = auth_service_pb2.AuthRequest(username="someuser", password="password")

            with pytest.raises(grpc.RpcError) as rpc_error_info:
                await stub.RegisterUser(request)

            assert rpc_error_info.value.code() == grpc.StatusCode.UNKNOWN # Changed from INTERNAL to UNKNOWN

    mock_user_service.create_user.assert_not_called() # create_user не должен быть вызван
