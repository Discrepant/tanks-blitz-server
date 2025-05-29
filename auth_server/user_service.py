# auth_server/user_service.py
# This module provides functions for user management,
# such as authentication and registration.
# It currently uses an in-memory dictionary as a mock database.
import asyncio
import logging # Added import for logging

logger = logging.getLogger(__name__) # Initialize logger for this module

# MOCK_USERS_DB: In-memory storage for user data.
# Key - username (string), Value - password (string).
# This data structure is used to simulate user account storage.
# In a real application, this would involve interaction with a proper database (e.g., PostgreSQL).
MOCK_USERS_DB = {
    "player1": "password123",          # Existing user
    "testuser": "testpass",           # Existing user
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
    logger.debug(f"Attempting to authenticate user '{username}' using MOCK_USERS_DB.")
    
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
    Asynchronously registers a new user.

    Checks if the username already exists in MOCK_USERS_DB. If not,
    adds the new user. Passwords are stored in plain text as per current MOCK_USERS_DB structure.

    Args:
        username (str): The new username.
        password (str): The new user's password.

    Returns:
        dict: A dictionary containing the status of the registration
              (e.g., {"status": "success", "message": "User registered successfully"} or
               {"status": "error", "message": "Username already exists"}).
    """
    logger.debug(f"Attempting to register new user '{username}'.")
    await asyncio.sleep(0.01) # Simulate a small delay, like a DB call.

    if username in MOCK_USERS_DB:
        logger.warning(f"Attempt to register existing username '{username}'.")
        return {"status": "error", "message": "Username already exists"}
    
    # Add the new user to the mock database.
    MOCK_USERS_DB[username] = password
    # In a real application, password hashing would be necessary here.
    logger.info(f"User '{username}' registered successfully.")
    return {"status": "success", "message": "User registered successfully"}
