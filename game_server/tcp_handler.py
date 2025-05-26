import asyncio
from .game_logic import GameRoom, Player

async def handle_game_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, game_room: GameRoom):
    addr = writer.get_extra_info('peername')
    print(f"Новое игровое подключение от {addr}")
    player = None # Инициализируем player как None

    try:
        # Первый шаг - аутентификация или регистрация через игровой сервер
        # В реальном приложении это может быть сложнее, например, ожидание токена
        intro_data = await reader.readuntil(b"\n")
        intro_message = intro_data.decode().strip()
        print(f"Получено для аутентификации/регистрации от {addr}: {intro_message}")

        parts = intro_message.split()
        command = parts[0].upper()

        if command == 'LOGIN' and len(parts) == 3:
            _, username, password = parts
            authenticated, auth_message, session_token = await game_room.authenticate_player(username, password)
            if authenticated:
                player = Player(writer, username, session_token) # Используем session_token
                await game_room.add_player(player)
                writer.write(f"LOGIN_SUCCESS {auth_message} Token: {session_token}\n".encode())
            else:
                writer.write(f"LOGIN_FAILURE {auth_message}\n".encode())
                return # Закрываем соединение, если логин не удался
        elif command == 'REGISTER' and len(parts) == 3:
            _, username, password = parts
            # Заглушка для регистрации через игровой сервер, если нужно
            # success, message = await game_room.register_player(username, password)
            # writer.write(f"{message}\n".encode())
            # Пока не реализовано, отправляем ошибку
            writer.write("REGISTER_FAILURE Регистрация через игровой сервер пока не поддерживается.\n".encode())
            return
        else:
            writer.write("INVALID_COMMAND Ожидается: LOGIN username password или REGISTER username password\n".encode())
            return # Закрываем соединение при неверной начальной команде

        await writer.drain()

        if not player or not player.writer: # Убедимся, что player создан и writer доступен
            print(f"Ошибка: игрок не был создан или writer отсутствует для {addr}")
            return

        # Основной цикл обработки команд от игрока
        while True:
            if player.writer.is_closing():
                break
            try:
                data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=300.0) # 5 минут таймаут
                message = data.decode().strip()
                if not message: # Пустое сообщение от клиента, возможно, соединение закрывается
                    print(f"Получено пустое сообщение от {player.name}, соединение может закрываться.")
                    break

                print(f"Получено от {player.name} ({addr}): {message}")
                await game_room.handle_player_command(player, message)

            except asyncio.TimeoutError:
                print(f"Таймаут ожидания сообщения от {player.name} ({addr}).")
                await player.send_message("SERVER: Вы были отключены из-за неактивности.")
                break
            except asyncio.IncompleteReadError:
                print(f"Клиент {player.name} ({addr}) закрыл соединение (IncompleteReadError).")
                break
            except ConnectionResetError:
                print(f"Соединение сброшено клиентом {player.name} ({addr}).")
                break
            except Exception as e:
                print(f"Ошибка при обработке команды от {player.name} ({addr}): {e}")
                await player.send_message(f"SERVER_ERROR: Произошла ошибка: {e}")
                break
    except Exception as e:
        print(f"Критическая ошибка в handle_game_client для {addr}: {e}")
        if writer and not writer.is_closing():
            try:
                writer.write(f"CRITICAL_ERROR {e}\n".encode())
                await writer.drain()
            except Exception as we:
                print(f"Не удалось отправить сообщение об ошибке клиенту {addr}: {we}")
    finally:
        if player:
            await game_room.remove_player(player)
            print(f"Игрок {player.name} ({addr}) отключен.")
        else:
            print(f"Соединение с {addr} закрыто (игрок не был полностью добавлен).")

        if writer and not writer.is_closing():
            writer.close()
            await writer.wait_closed()
