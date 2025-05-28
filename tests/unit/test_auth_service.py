# tests/unit/test_auth_service.py
# Этот файл содержит модульные тесты для сервиса аутентификации пользователей
# (`auth_server.user_service.py`) с использованием pytest.
import pytest # Импортируем pytest для написания и запуска тестов
from unittest.mock import patch # Импортируем patch из unittest.mock для мокирования объектов
# Импортируем тестируемые функции и MOCK_USERS_DB из модуля user_service
from auth_server.user_service import authenticate_user, MOCK_USERS_DB, register_user

# pytest помечает асинхронные тестовые функции с помощью @pytest.mark.asyncio,
# но если используется pytest-asyncio, достаточно просто объявить функцию как async def.
# Предполагаем, что pytest-asyncio настроен.

@pytest.mark.asyncio
async def test_authenticate_user_success():
    """
    Тест успешной аутентификации пользователя.
    Проверяет, что функция `authenticate_user` корректно аутентифицирует
    существующего пользователя с правильным паролем.
    """
    # Используем тестовых пользователей, которые должны быть в MOCK_USERS_DB.
    # Если MOCK_USERS_DB инициализируется при импорте, эти пользователи уже там.
    # В противном случае, их нужно добавить в MOCK_USERS_DB перед тестом или использовать мок.
    test_username = "player1"
    test_password = "password123" # Предполагаемый пароль для player1
    is_auth, message = await authenticate_user(test_username, test_password)
    assert is_auth is True, "Аутентификация должна быть успешной для корректных учетных данных."
    assert "authenticated successfully" in message, "Сообщение должно подтверждать успешную аутентификацию."

@pytest.mark.asyncio
async def test_authenticate_user_wrong_password():
    """
    Тест аутентификации пользователя с неверным паролем.
    Проверяет, что `authenticate_user` не аутентифицирует пользователя,
    если предоставлен неверный пароль.
    """
    test_username = "player1" # Существующий пользователь
    wrong_password = "wrongpassword" # Неверный пароль
    is_auth, message = await authenticate_user(test_username, wrong_password)
    assert is_auth is False, "Аутентификация не должна проходить с неверным паролем."
    assert "Incorrect password" in message, "Сообщение должно указывать на неверный пароль."

@pytest.mark.asyncio
async def test_authenticate_user_not_found():
    """
    Тест аутентификации несуществующего пользователя.
    Проверяет, что `authenticate_user` не аутентифицирует пользователя,
    которого нет в базе данных (MOCK_USERS_DB).
    """
    unknown_username = "unknownuser" # Несуществующий пользователь
    test_password = "password123"
    is_auth, message = await authenticate_user(unknown_username, test_password)
    assert is_auth is False, "Аутентификация не должна проходить для несуществующего пользователя."
    assert "not found" in message, "Сообщение должно указывать, что пользователь не найден."

@pytest.mark.asyncio
async def test_register_user_success_mock():
    """
    Тест успешной регистрации нового пользователя (с использованием мока для MOCK_USERS_DB).
    Проверяет, что функция `register_user` (в ее текущей mock-реализации)
    возвращает успешный результат для нового пользователя.
    """
    # Мокаем MOCK_USERS_DB для этого конкретного теста, чтобы изолировать его
    # и не влиять на другие тесты, которые могут полагаться на исходное состояние MOCK_USERS_DB.
    # `clear=True` очищает словарь перед применением патча.
    # Хотя `register_user` в текущей реализации ничего не меняет в MOCK_USERS_DB (строка закомментирована),
    # этот подход демонстрирует, как можно было бы тестировать, если бы изменение происходило.
    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {}, clear=True):
        new_username = "newbie"
        new_password = "newpassword"
        is_registered, message = await register_user(new_username, new_password)
        assert is_registered is True, "Регистрация нового пользователя должна быть успешной."
        assert "successfully registered" in message, "Сообщение должно подтверждать успешную регистрацию."
        # В реальном тесте, если бы `register_user` действительно добавлял пользователя,
        # мы бы проверили, что пользователь добавлен в MOCK_USERS_DB:
        # `assert new_username in MOCK_USERS_DB`
        # или что был вызван соответствующий метод сохранения в базу данных.

@pytest.mark.asyncio
async def test_register_user_already_exists_mock():
    """
    Тест попытки регистрации пользователя, который уже существует (с моком MOCK_USERS_DB).
    Проверяет, что `register_user` возвращает ошибку, если пользователь с таким именем
    уже присутствует в системе.
    """
    existing_username = "player1_for_register_test" # Используем уникальное имя для этого теста
    # Убедимся, что пользователь существует в MOCK_USERS_DB на время этого теста.
    # Используем patch.dict для временного изменения MOCK_USERS_DB.
    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {existing_username: "password123"}, clear=True):
        is_registered, message = await register_user(existing_username, "anypass")
        assert is_registered is False, "Регистрация существующего пользователя должна завершиться неудачей."
        assert "already exists" in message, "Сообщение должно указывать, что пользователь уже существует."
