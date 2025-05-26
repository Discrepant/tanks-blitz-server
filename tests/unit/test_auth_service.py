# tests/unit/test_auth_service.py
import pytest
from auth_server.user_service import authenticate_user, MOCK_USERS_DB, register_user

@pytest.mark.asyncio
async def test_authenticate_user_success():
    # Используем тестовых пользователей из MOCK_USERS_DB
    test_username = "player1"
    test_password = "password123"
    is_auth, message = await authenticate_user(test_username, test_password)
    assert is_auth is True
    assert "успешно аутентифицирован" in message

@pytest.mark.asyncio
async def test_authenticate_user_wrong_password():
    test_username = "player1"
    wrong_password = "wrongpassword"
    is_auth, message = await authenticate_user(test_username, wrong_password)
    assert is_auth is False
    assert "Неверный пароль" in message

@pytest.mark.asyncio
async def test_authenticate_user_not_found():
    unknown_username = "unknownuser"
    test_password = "password123"
    is_auth, message = await authenticate_user(unknown_username, test_password)
    assert is_auth is False
    assert "Пользователь не найден" in message

@pytest.mark.asyncio
async def test_register_user_success_mock(mocker):
    # Мокаем MOCK_USERS_DB для этого теста, чтобы не влиять на другие
    # Хотя register_user в текущей реализации ничего не меняет, это для примера
    mocker.patch.dict(MOCK_USERS_DB, {}, clear=True) 
    
    new_username = "newbie"
    new_password = "newpassword"
    is_registered, message = await register_user(new_username, new_password)
    assert is_registered is True
    assert "успешно зарегистрирован" in message
    # В реальном тесте мы бы проверили, что пользователь добавлен в MOCK_USERS_DB
    # или что был вызван метод сохранения в БД, если бы он был реализован.

@pytest.mark.asyncio
async def test_register_user_already_exists_mock(mocker):
    existing_username = "player1"
    # Убедимся, что пользователь существует для этого теста
    mocker.patch.dict(MOCK_USERS_DB, {existing_username: "password123"}, clear=True)

    is_registered, message = await register_user(existing_username, "anypass")
    assert is_registered is False
    assert "уже существует" in message
