import asyncio

# Заглушка для базы данных пользователей
MOCK_USERS_DB = {
    "player1": "password123",
    "testuser": "testpass"
}

async def authenticate_user(username, password):
    """
    Асинхронная функция для аутентификации пользователя.
    Пока что использует заглушку.
    Возвращает (bool, str): (успех_аутентификации, сообщение)
    """
    await asyncio.sleep(0.01) # Имитация задержки обращения к БД

    if username in MOCK_USERS_DB and MOCK_USERS_DB[username] == password:
        # В реальном приложении здесь бы генерировался и возвращался токен сессии
        return True, f"Пользователь {username} успешно аутентифицирован."
    elif username in MOCK_USERS_DB:
        return False, "Неверный пароль."
    else:
        return False, "Пользователь не найден."

async def register_user(username, password):
    """
    Асинхронная функция для регистрации нового пользователя.
    Пока что не реализована полностью, только заглушка.
    """
    await asyncio.sleep(0.01)
    if username in MOCK_USERS_DB:
        return False, "Пользователь с таким именем уже существует."
    # MOCK_USERS_DB[username] = password # В реальном приложении здесь было бы сохранение в БД
    return True, f"Пользователь {username} успешно зарегистрирован (заглушка)."
