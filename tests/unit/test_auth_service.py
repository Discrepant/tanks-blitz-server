# tests/unit/test_auth_service.py
# Этот файл содержит модульные тесты для сервиса аутентификации пользователей
# (`auth_server.user_service.py`) с использованием pytest.
import pytest # Импортируем pytest для написания и запуска тестов
from unittest.mock import patch # Импортируем patch из unittest.mock для мокирования объектов
# Импортируем UserService и MOCK_USERS_DB из модуля user_service
from auth_server.user_service import UserService, MOCK_USERS_DB

# pytest помечает асинхронные тестовые функции с помощью @pytest.mark.asyncio,
# но если используется pytest-asyncio, достаточно просто объявить функцию как async def.
# Предполагаем, что pytest-asyncio настроен.

async def test_authenticate_user_success():
    """
    Тест успешной аутентификации пользователя.
    Проверяет, что метод `authenticate_user` экземпляра `UserService`
    корректно аутентифицирует существующего пользователя с правильным паролем.
    """
    user_service = UserService()
    test_username = "player1"
    test_password = "password123" # Пароль для player1 в MOCK_USERS_DB
    # Используем исходный MOCK_USERS_DB, так как он содержит player1
    is_auth, message = await user_service.authenticate_user(test_username, test_password)
    assert is_auth is True, "Аутентификация должна быть успешной для корректных учетных данных."
    assert "успешно аутентифицирован" in message, "Сообщение должно подтверждать успешную аутентификацию." # Ожидаем русский текст

async def test_authenticate_user_wrong_password():
    """
    Тест аутентификации пользователя с неверным паролем.
    Проверяет, что `authenticate_user` не аутентифицирует пользователя,
    если предоставлен неверный пароль.
    """
    user_service = UserService()
    test_username = "player1" # Существующий пользователь
    wrong_password = "wrongpassword" # Неверный пароль
    is_auth, message = await user_service.authenticate_user(test_username, wrong_password)
    assert is_auth is False, "Аутентификация не должна проходить с неверным паролем."
    assert "Неверный пароль" in message, "Сообщение должно указывать на неверный пароль." # Ожидаем русский текст

async def test_authenticate_user_not_found():
    """
    Тест аутентификации несуществующего пользователя.
    Проверяет, что `authenticate_user` не аутентифицирует пользователя,
    которого нет в базе данных.
    """
    user_service = UserService()
    unknown_username = "unknownuser" # Несуществующий пользователь
    test_password = "password123"
    # Используем patch.dict для гарантии, что MOCK_USERS_DB не содержит unknownuser,
    # хотя по умолчанию его там и нет. Это также демонстрирует использование patch.dict.
    # Копируем текущее состояние MOCK_USERS_DB, чтобы не потерять существующих пользователей для других тестов,
    # если бы они выполнялись параллельно или в другом порядке и зависели от состояния.
    # Однако, pytest обычно изолирует тесты. Для чистоты, можно передать исходный MOCK_USERS_DB.
    # В данном случае, так как мы проверяем отсутствие, достаточно исходного состояния.
    is_auth, message = await user_service.authenticate_user(unknown_username, test_password)
    assert is_auth is False, "Аутентификация не должна проходить для несуществующего пользователя."
    assert "Пользователь не найден" in message, "Сообщение должно указывать, что пользователь не найден." # Ожидаем русский текст

async def test_create_user_success():
    """
    Тест успешной регистрации нового пользователя с использованием UserService.create_user.
    Проверяет, что метод `create_user` добавляет пользователя в MOCK_USERS_DB.
    """
    user_service = UserService()
    new_username = "newbie"
    # create_user ожидает хешированный пароль
    hashed_password = "hashed_new_password"

    # Используем patch.dict для изоляции изменений в MOCK_USERS_DB
    # `clear=True` создаст пустой MOCK_USERS_DB для этого теста,
    # но нам нужно сохранить существующих пользователей, если бы другие части теста их использовали.
    # Лучше скопировать и модифицировать, или просто проверить добавление.
    # Для этого теста, мы хотим начать с чистого или контролируемого состояния для new_username.
    # Мы будем проверять, что пользователь добавляется.
    initial_users = MOCK_USERS_DB.copy()
    if new_username in initial_users: # Удаляем, если он там есть от предыдущих тестов (маловероятно с patch.dict)
        del initial_users[new_username]

    with patch.dict('auth_server.user_service.MOCK_USERS_DB', initial_users, clear=True):
        is_created, message = await user_service.create_user(new_username, hashed_password)
        assert is_created is True, "Регистрация нового пользователя должна быть успешной."
        assert "успешно создан" in message or "успешно зарегистрирован" in message, "Сообщение должно подтверждать успешную регистрацию/создание." # Ожидаем русский текст
        # Проверяем, что пользователь действительно добавлен в MOCK_USERS_DB с хешированным паролем
        assert new_username in MOCK_USERS_DB, "Пользователь должен быть добавлен в MOCK_USERS_DB."
        assert MOCK_USERS_DB[new_username] == hashed_password, "Хешированный пароль должен быть сохранен."

async def test_create_user_already_exists():
    """
    Тест попытки регистрации пользователя, который уже существует, с использованием UserService.create_user.
    """
    user_service = UserService()
    existing_username = "player1" # Пользователь, который уже есть в MOCK_USERS_DB
    hashed_password = "hashed_password_for_existing"

    # Убедимся, что пользователь существует. Используем исходный MOCK_USERS_DB.
    # patch.dict здесь используется для гарантии, что состояние MOCK_USERS_DB известно
    # и для демонстрации его использования, хотя MOCK_USERS_DB уже содержит player1.
    # Мы не используем clear=True, чтобы сохранить исходных пользователей.
    # Вместо этого, мы передаем копию MOCK_USERS_DB, чтобы любые изменения
    # внутри with не затрагивали глобальное состояние MOCK_USERS_DB после теста.
    # Но так как create_user модифицирует MOCK_USERS_DB напрямую,
    # нам нужно передать словарь, который будет модифицирован, и затем проверить его.
    # Или, если мы хотим проверить, что он НЕ добавляет, если пользователь существует,
    # то нам не нужно, чтобы MOCK_USERS_DB изменялся.
    # UserService.create_user изменяет глобальный MOCK_USERS_DB.
    # Поэтому patch.dict должен применяться к 'auth_server.user_service.MOCK_USERS_DB'.

    # Создаем копию, чтобы не изменять оригинальный MOCK_USERS_DB другими тестами
    # и явно задаем пользователя, который должен существовать.
    users_db_for_test = MOCK_USERS_DB.copy()
    users_db_for_test[existing_username] = "original_password123" # Убеждаемся, что он есть

    with patch.dict('auth_server.user_service.MOCK_USERS_DB', users_db_for_test, clear=True):
        is_created, message = await user_service.create_user(existing_username, hashed_password)
        assert is_created is False, "Регистрация существующего пользователя должна завершиться неудачей."
        assert "уже существует" in message, "Сообщение должно указывать, что пользователь уже существует." # Ожидаем русский текст
        # Убедимся, что пароль не был изменен для существующего пользователя
        assert MOCK_USERS_DB[existing_username] == "original_password123", "Пароль существующего пользователя не должен изменяться."

async def test_create_user_mock_db_interaction():
    """
    Тест для проверки, что MOCK_USERS_DB корректно изменяется при регистрации.
    """
    user_service = UserService()
    test_user = "test_add_user"
    test_hashed_pass = "test_hashed_pass"

    # Начнем с пустого MOCK_USERS_DB для этого теста, чтобы точно проверить добавление
    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {}, clear=True) as mocked_db:
        assert test_user not in mocked_db, "Пользователь не должен существовать в начале теста."

        is_created, _ = await user_service.create_user(test_user, test_hashed_pass)
        assert is_created is True, "Создание пользователя должно быть успешным."

        # mocked_db здесь будет ссылаться на пропатченный словарь
        assert test_user in mocked_db, "Пользователь должен быть добавлен в MOCK_USERS_DB."
        assert mocked_db[test_user] == test_hashed_pass, "Хешированный пароль должен быть сохранен."

        # Попытка добавить того же пользователя еще раз
        is_created_again, _ = await user_service.create_user(test_user, test_hashed_pass)
        assert is_created_again is False, "Повторное создание пользователя должно завершиться неудачей."


async def test_authenticate_newly_created_user_with_hash_as_password():
    """
    Тест аутентификации нового пользователя, используя сохраненный хеш как пароль.
    Это проверяет, что если MOCK_USERS_DB содержит хеш, и тот же хеш передан
    в authenticate_user, аутентификация проходит.
    """
    user_service = UserService()
    username = "newly_created_user"
    password_hash = "test_hash123" # Это будет и сохраненный "пароль", и переданный для аутентификации

    with patch.dict('auth_server.user_service.MOCK_USERS_DB', {}, clear=True) as mocked_db:
        # 1. Создаем пользователя
        is_created, msg_create = await user_service.create_user(username, password_hash)
        assert is_created is True, f"Не удалось создать пользователя: {msg_create}"
        assert username in mocked_db, "Пользователь должен быть в mocked_db после создания."
        assert mocked_db[username] == password_hash, "Сохраненный пароль должен быть хешем."

        # 2. Пытаемся аутентифицировать с правильным хешем
        is_auth_success, msg_auth_success = await user_service.authenticate_user(username, password_hash)
        assert is_auth_success is True, \
            f"Аутентификация с правильным хешем должна быть успешной. Сообщение: {msg_auth_success}"
        assert "успешно аутентифицирован" in msg_auth_success, \
            "Сообщение об успехе аутентификации неверно." # Ожидаем русский текст

        # 3. Пытаемся аутентифицировать с неправильным хешем/паролем
        wrong_password = "wrong_hash_or_password"
        is_auth_fail, msg_auth_fail = await user_service.authenticate_user(username, wrong_password)
        assert is_auth_fail is False, \
            "Аутентификация с неправильным хешем/паролем должна быть неуспешной."
        assert "Неверный пароль" in msg_auth_fail, \
            "Сообщение о неверном пароле неверно при аутентификации с неправильным хешем." # Ожидаем русский текст

def test_initialize_redis_client_static_method():
    """
    Тест статического метода UserService.initialize_redis_client().
    Проверяет, что метод вызывается без ошибок (не выбрасывает исключений).
    """
    try:
        UserService.initialize_redis_client()
        # Если метод выполнился без исключений, тест считается пройденным.
        # Можно добавить mock для logger и проверить, что логирование происходит,
        # но для простой заглушки это может быть излишним.
    except Exception as e:
        pytest.fail(f"UserService.initialize_redis_client() вызвал исключение: {e}")
