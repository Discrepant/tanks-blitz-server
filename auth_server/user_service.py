# auth_server/user_service.py
# Этот модуль предоставляет функции для управления пользователями,
# такие как аутентификация и регистрация.
# В текущей реализации используется mock-база данных.
import asyncio
import logging # Добавлен импорт для логирования

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

# MOCK_USERS_DB: Заглушка для базы данных пользователей.
# Ключ - имя пользователя (строка), значение - пароль (строка).
# Эта структура данных используется для имитации хранения учетных записей.
# В реальном приложении здесь было бы взаимодействие с настоящей базой данных (например, PostgreSQL).
MOCK_USERS_DB = {
    "player1": "password123",          # Существующий пользователь
    "testuser": "testpass",           # Существующий пользователь
    "integ_user": "integ_pass",       # Пользователь для интеграционного теста test_01
    "integ_user_fail": "correct_pass",# Пользователь для интеграционного теста test_02 (неудачная аутентификация)
    "integ_user2": "integ_pass2"      # Пользователь для интеграционного теста test_08 (чат)
}

async def authenticate_user(username, password):
    """
    Асинхронная функция для аутентификации пользователя по имени и паролю.

    Имитирует обращение к базе данных для проверки учетных данных.
    В реальном приложении здесь бы выполнялся запрос к БД и проверка хеша пароля.

    Args:
        username (str): Имя пользователя.
        password (str): Пароль пользователя.

    Returns:
        tuple[bool, str]: Кортеж, где первый элемент - булево значение
                          (True при успехе, False при неудаче), а второй -
                          сообщение о результате аутентификации (может содержать
                          токен сессии или описание ошибки).
    """
    # Логирование текущей mock-базы данных для отладки.
    # В продакшене следует избегать логирования чувствительных данных, таких как вся база пользователей.
    logger.debug(f"Попытка аутентификации пользователя '{username}' с использованием MOCK_USERS_DB.")
    
    await asyncio.sleep(0.01) # Имитация небольшой задержки, как при обращении к БД.

    if username in MOCK_USERS_DB and MOCK_USERS_DB[username] == password:
        # Успешная аутентификация.
        # В реальном приложении здесь бы генерировался и возвращался сессионный токен (например, JWT).
        # Текущее сообщение "Пользователь {username} успешно аутентифицирован." может быть использовано
        # клиентом или сервером для подтверждения, или заменено на токен.
        logger.info(f"User '{username}' authenticated successfully.")
        return True, f"User {username} authenticated successfully." # В будущем здесь может быть токен
    elif username in MOCK_USERS_DB:
        # Пользователь найден, но пароль неверный.
        logger.warning(f"Failed authentication attempt for user '{username}': incorrect password.")
        return False, "Incorrect password."
    else:
        # Пользователь не найден в базе данных.
        logger.warning(f"Failed authentication attempt: user '{username}' not found.")
        return False, "User not found."

async def register_user(username, password):
    """
    Асинхронная функция для регистрации нового пользователя.

    В текущей реализации это заглушка, которая проверяет, существует ли уже
    пользователь с таким именем, но фактически не сохраняет нового пользователя
    в MOCK_USERS_DB на постоянной основе (изменение MOCK_USERS_DB в этой функции
    закомментировано, чтобы не влиять на другие тесты, ожидающие исходное состояние).
    В реальном приложении здесь бы происходило сохранение нового пользователя в базу данных,
    включая хеширование пароля.

    Args:
        username (str): Имя нового пользователя.
        password (str): Пароль нового пользователя.

    Returns:
        tuple[bool, str]: Кортеж, где первый элемент - булево значение
                          (True при успехе регистрации, False при неудаче),
                          а второй - сообщение о результате.
    """
    logger.debug(f"Attempting to register new user '{username}'.")
    await asyncio.sleep(0.01) # Имитация задержки обращения к БД.

    if username in MOCK_USERS_DB:
        logger.warning(f"Attempt to register existing user '{username}'.")
        return False, "User with this name already exists."
    
    # Строка ниже закомментирована, чтобы MOCK_USERS_DB оставалась неизменной во время тестов.
    # В реальном приложении здесь было бы сохранение в БД:
    # MOCK_USERS_DB[username] = password
    # Также необходимо было бы хешировать пароль перед сохранением.
    logger.info(f"User '{username}' successfully registered (stub).")
    return True, f"User {username} successfully registered (stub)."
