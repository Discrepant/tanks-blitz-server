# auth_server/tcp_handler.py
import asyncio
from .user_service import authenticate_user
from .main import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импорт метрик

async def handle_auth_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info('peername')
    print(f"Новое подключение от {addr}")
    ACTIVE_CONNECTIONS_AUTH.inc() # Увеличиваем счетчик активных соединений

    try:
        data = await reader.read(1024)
        message = data.decode().strip()
        print(f"Получено от {addr}: {message}")

        parts = message.split()
        if len(parts) == 3 and parts[0].upper() == 'LOGIN':
            _, username, password = parts
            is_authenticated, response_message = await authenticate_user(username, password)
            if is_authenticated:
                SUCCESSFUL_AUTHS.inc() # Увеличиваем счетчик успешных аутентификаций
                writer.write(f"AUTH_SUCCESS {response_message}\n".encode())
            else:
                FAILED_AUTHS.inc() # Увеличиваем счетчик неудачных аутентификаций
                writer.write(f"AUTH_FAILURE {response_message}\n".encode())
        else:
            writer.write("INVALID_COMMAND Формат: LOGIN username password\n".encode())

        await writer.drain()
    except Exception as e:
        print(f"Ошибка при обработке клиента {addr}: {e}")
        FAILED_AUTHS.inc() # Также можно считать это неудачной попыткой
        writer.write(f"ERROR_INTERNAL_SERVER_ERROR {e}\n".encode())
        await writer.drain()
    finally:
        print(f"Соединение с {addr} закрыто")
        ACTIVE_CONNECTIONS_AUTH.dec() # Уменьшаем счетчик активных соединений
        writer.close()
        await writer.wait_closed()
