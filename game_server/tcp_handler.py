# game_server/tcp_handler.py
# Этот модуль отвечает за обработку TCP-соединений от игровых клиентов.
# Включает аутентификацию, обработку команд и взаимодействие с игровой комнатой.
import asyncio
import json  # Добавлен импорт для возможной работы с JSON, хотя текущие команды текстовые
import logging  # Добавлен импорт для логирования
import time # Добавлен импорт (может быть полезен для временных меток или задержек)
from .game_logic import GameRoom, Player # Импортируем GameRoom и Player из game_logic
# Убедитесь, что пути импорта верны. Если message_broker_clients в core, то from core.message_broker_clients ...
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS  
logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля


async def handle_game_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, game_room: GameRoom):
    """
    Асинхронный обработчик для каждого подключенного игрового клиента по TCP.

    Читает команды от клиента, обрабатывает их (LOGIN, REGISTER, MOVE, SHOOT)
    и взаимодействует с GameRoom. Команды MOVE и SHOOT публикуются в RabbitMQ.

    Args:
        reader (asyncio.StreamReader): Объект для чтения данных от клиента.
        writer (asyncio.StreamWriter): Объект для записи данных клиенту.
        game_room (GameRoom): Экземпляр игровой комнаты для взаимодействия.
    """
    addr = writer.get_extra_info('peername') # Получаем адрес клиента (IP, порт)
    logger.info(f"Новое TCP-соединение от {addr}")
    player: Player | None = None # Переменная для хранения объекта Player после успешного логина
    
    try:
        while True: # Основной цикл обработки команд от клиента
            data = await reader.readuntil(b'\n') # Читаем данные до символа новой строки
            message_str = data.decode('utf-8').strip() # Декодируем и удаляем пробельные символы
            
            if not message_str: # Если получена пустая строка
                logger.warning(f"От {addr} получена пустая командная строка.")
                writer.write("EMPTY_COMMAND\n".encode('utf-8')) # Отправляем ошибку клиенту
                await writer.drain()
                continue # Переходим к следующей итерации цикла

            parts = message_str.split() # Разделяем команду и аргументы
            if not parts: # Если после разделения ничего не осталось (маловероятно после strip, но для надежности)
                continue

            cmd = parts[0].upper() # Первое слово - команда, приводим к верхнему регистру
            
            # Обработка команды LOGIN
            if cmd == 'LOGIN' and len(parts) == 3:
                username, password = parts[1], parts[2]
                # Вызываем метод аутентификации из игровой комнаты
                authenticated, auth_message, session_token = await game_room.authenticate_player(username, password)
                logger.debug(f"GameTCPHandler: authenticate_player вернул: auth={authenticated}, msg='{auth_message}', token='{session_token}'")
                
                if authenticated:
                    # Создаем экземпляр Player
                    # Предполагается, что Player импортирован корректно (например, из .models или .game_logic)
                    player_obj = Player(writer=writer, name=username, session_token=session_token)
                    # Добавляем объект игрока в игровую комнату
                    await game_room.add_player(player_obj) 
                    player = player_obj # Присваиваем объект игрока переменной обработчика
                    
                    # Отправляем успешный ответ
                    response_msg = f"LOGIN_SUCCESS {auth_message} Token: {session_token if session_token else 'N/A'}\n"
                    logger.debug(f"GameTCPHandler: Отправка LOGIN_SUCCESS клиенту. Сообщение='{auth_message}', Токен='{session_token if session_token else 'N/A'}'")
                    writer.write(response_msg.encode('utf-8'))
                    await writer.drain()
                    logger.info(f"Игрок {username} вошел в систему с {addr}. Токен: {session_token if session_token else 'N/A'}")
                else:
                    # Отправляем ответ о неудаче
                    response_msg = f"LOGIN_FAILURE {auth_message}\n"
                    logger.debug(f"GameTCPHandler: Отправка LOGIN_FAILURE клиенту. Сообщение='{auth_message}'")
                    writer.write(response_msg.encode('utf-8'))
                    await writer.drain()
                    logger.info(f"Неудачный вход для {username} с {addr}. Сообщение: {auth_message}. Завершение обработчика.")
                    return  # Завершаем обработчик для этого клиента
            
            # Обработка команды REGISTER (заглушка)
            elif cmd == 'REGISTER' and len(parts) == 3:
                # Регистрация через игровой сервер пока не поддерживается или обрабатывается иначе
                writer.write("REGISTER_FAILURE Регистрация через игровой сервер пока не поддерживается.\n".encode('utf-8'))
                await writer.drain()
                logger.info(f"REGISTER_FAILURE отправлен {addr}. Завершение обработчика.")
                return # Завершаем обработчик
            
            # Обработка команд MOVE или SHOOT
            elif cmd == 'MOVE' or cmd == 'SHOOT':
                if not player: # Если игрок не аутентифицирован
                    writer.write("UNAUTHORIZED Сначала необходимо войти в систему\n".encode('utf-8'))
                    await writer.drain()
                    continue

                if cmd == 'MOVE':
                    if len(parts) < 3: # Проверяем наличие координат
                        writer.write("MOVE_ERROR Отсутствуют координаты\n".encode('utf-8'))
                        await writer.drain()
                        continue
                    try:
                        x = int(parts[1]) # X координата
                        y = int(parts[2]) # Y координата
                        # Формируем данные команды для отправки в RabbitMQ
                        command_data = {
                            "player_id": player.name, # Используем имя игрока как ID
                            "command": "move",
                            "details": {"new_position": [x, y]}
                        }
                        # Публикуем команду в RabbitMQ
                        await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                        logger.info(f"Команда MOVE от {player.name} ({x},{y}) опубликована в RabbitMQ.")
                        writer.write("COMMAND_RECEIVED MOVE\n".encode('utf-8')) # Отправляем подтверждение
                        await writer.drain()
                    except ValueError:
                        writer.write("MOVE_ERROR Invalid coordinates\n".encode('utf-8')) # Локализация сообщения об ошибке
                        await writer.drain()
                        logger.error(f"Неверные координаты для команды MOVE от {player.name}: {parts[1:]}")
                        continue
                elif cmd == 'SHOOT':
                    # Формируем данные команды для отправки в RabbitMQ
                    command_data = {
                        "player_id": player.name,
                        "command": "shoot",
                        "details": {"source": "tcp_handler"} # Дополнительная информация об источнике
                    }
                    # Публикуем команду в RabbitMQ
                    await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                    logger.info(f"Команда SHOOT от {player.name} опубликована в RabbitMQ.")
                    writer.write("COMMAND_RECEIVED SHOOT\n".encode('utf-8')) # Отправляем подтверждение
                    await writer.drain()
            
            # Обработка других команд (например, из GameRoom.handle_player_command)
            elif player and cmd in ["SAY", "HELP", "PLAYERS", "QUIT"]:
                # Передаем команду в игровую комнату для обработки логики чата и информации
                await game_room.handle_player_command(player, message_str)
                # Ответы игроку будут отправлены из game_room.handle_player_command через player.send_message
                # Если команда QUIT, то соединение будет закрыто там же.
                if cmd == "QUIT": # Если QUIT, то handle_player_command инициирует закрытие
                    logger.info(f"Игрок {player.name} отправил QUIT. Соединение будет закрыто.")
                    # Цикл прервется, когда writer закроется и readuntil вызовет исключение
            
            else: # Неизвестная команда
                logger.warning(f"Неизвестная команда '{cmd}' от {player.name if player else addr}. Полное сообщение: '{message_str}'")
                # Независимо от того, залогинен ли игрок, если команда не распознана этим основным блоком if/elif,
                # отправляем стандартизированный UNKNOWN_COMMAND.
                # Логика SAY, HELP, PLAYERS, QUIT обрабатывается выше и имеет свои ответы.
                writer.write("UNKNOWN_COMMAND\n".encode('utf-8'))
                await writer.drain()

            # Подтверждение получения команды (если команда не QUIT и не вызвала ошибку ранее)
            # Этот ответ может быть избыточен, если game_room.handle_player_command уже отправил ответ.
            # Для MOVE/SHOOT ответ не обязателен, так как они асинхронны.
            # if cmd not in ["QUIT", "LOGIN", "REGISTER"] and (cmd in ["MOVE", "SHOOT"] or player): # Только если это не команды, завершающие соединение или уже обработанные
            #     pass # Убрали общий COMMAND_RECEIVED, так как ответы теперь специфичны для команд MOVE/SHOOT или обрабатываются в GameRoom

    except ConnectionResetError:
        logger.info(f"Connection reset by client {player.name if player else addr} ({addr}).")
    except asyncio.IncompleteReadError:
        logger.info(f"Client {player.name if player else addr} ({addr}) closed connection (IncompleteReadError).")
    except Exception as e:
        logger.critical(f"Critical error in handle_game_client for {addr}: {e}", exc_info=True)
        if writer and not writer.is_closing(): # Если writer все еще открыт
            try:
                # Пытаемся уведомить клиента о критической ошибке
                writer.write(f"CRITICAL_SERVER_ERROR {type(e).__name__}\n".encode('utf-8'))
                await writer.drain()
            except Exception as we:
                logger.error(f"Could not send critical error message to client {addr}: {we}")
    finally:
        logger.info(f"Finalizing processing for {addr}. Player: {player.name if player else 'N/A'}.")
        if player: # Если объект игрока был создан
            logger.info(f"Removing player {player.name} from game room {game_room}.")
            await game_room.remove_player(player) # Удаляем игрока из игровой комнаты
        
        # Закрываем writer, если он еще не закрыт
        if writer and not writer.is_closing():
            logger.debug(f"Closing writer for {addr} in finally block.")
            writer.close()
            try:
                await writer.wait_closed() # Ожидаем полного закрытия
            except Exception as e_close:
                logger.error(f"Error during writer.wait_closed() for {addr}: {e_close}", exc_info=True)
        logger.info(f"Connection with {addr} (player: {player.name if player else 'N/A'}) fully closed.")