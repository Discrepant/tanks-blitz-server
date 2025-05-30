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
    # logger.info(f"New TCP connection from {addr}")
    logger.debug(f"Handling new TCP connection from {addr}")

    # Send SERVER_ACK_CONNECTED message
    logger.debug(f"Attempting to send SERVER_ACK_CONNECTED to {addr}")
    writer.write("SERVER_ACK_CONNECTED\n".encode('utf-8'))
    await writer.drain()
    logger.info(f"Successfully sent SERVER_ACK_CONNECTED to {addr}")

    player: Player | None = None # Переменная для хранения объекта Player после успешного логина
    
    try:
        while True: # Основной цикл обработки команд от клиента
            data = await reader.readuntil(b'\n') # Читаем данные до символа новой строки
            message_str = data.decode('utf-8').strip() # Декодируем и удаляем пробельные символы
            logger.debug(f"Received message from {addr}: '{message_str}'")
            
            if not message_str: # Если получена пустая строка
                logger.warning(f"Empty command line received from {addr}.")
                writer.write("EMPTY_COMMAND\n".encode('utf-8')) # Отправляем ошибку клиенту
                logger.debug(f"Attempting to drain writer for {addr} after sending: EMPTY_COMMAND")
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
                    player = player_obj # Присваиваем объект игрока переменной обработчика
                    
                    # Отправляем успешный ответ ПЕРЕД добавлением в комнату, чтобы тест получил его первым
                    response_msg = f"LOGIN_SUCCESS {auth_message} Token: {session_token if session_token else 'N/A'}\n"
                    logger.debug(f"GameTCPHandler: Sending LOGIN_SUCCESS to client. Message='{auth_message}', Token='{session_token if session_token else 'N/A'}'")
                    writer.write(response_msg.encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: LOGIN_SUCCESS")
                    await writer.drain()
                    logger.info(f"Player {username} logged in from {addr} (LOGIN_SUCCESS sent). Token: {session_token if session_token else 'N/A'}")

                    # Теперь добавляем объект игрока в игровую комнату
                    # Это может отправить "Welcome" и другие сообщения комнаты
                    await game_room.add_player(player_obj)

                    # player_obj is created BEFORE this block by tcp_handler
                    # The Welcome message is sent from game_room.add_player()
                    # Add delay *after* welcome message is sent by add_player (or after LOGIN_SUCCESS)
                    await asyncio.sleep(0.02) # Increased diagnostic delay, kept for now
                else:
                    # Отправляем ответ о неудаче
                    response_msg = f"LOGIN_FAILURE {auth_message}\n"
                    logger.debug(f"GameTCPHandler: Sending LOGIN_FAILURE to client. Message='{auth_message}'")
                    writer.write(response_msg.encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: LOGIN_FAILURE")
                    await writer.drain()
                    logger.info(f"Failed login for {username} from {addr}. Message: {auth_message}. Terminating handler.")
                    return  # Завершаем обработчик для этого клиента
            
            # Обработка команды REGISTER (заглушка)
            elif cmd == 'REGISTER' and len(parts) == 3:
                # Регистрация через игровой сервер пока не поддерживается или обрабатывается иначе
                writer.write("REGISTER_FAILURE Registration via game server is not supported yet.\n".encode('utf-8')) # Already in English
                logger.debug(f"Attempting to drain writer for {addr} after sending: REGISTER_FAILURE")
                await writer.drain()
                logger.info(f"REGISTER_FAILURE sent to {addr}. Terminating handler.")
                return # Завершаем обработчик
            
            # Обработка команд MOVE или SHOOT
            elif cmd == 'MOVE' or cmd == 'SHOOT':
                if not player: # Если игрок не аутентифицирован
                    writer.write("UNAUTHORIZED You need to log in first\n".encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: UNAUTHORIZED")
                    await writer.drain()
                    continue

                if cmd == 'MOVE':
                    if len(parts) < 3: # Проверяем наличие координат
                        writer.write("MOVE_ERROR Coordinates are missing\n".encode('utf-8'))
                        logger.debug(f"Attempting to drain writer for {addr} after sending: MOVE_ERROR Coordinates are missing")
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
                        logger.info(f"MOVE command from {player.name} ({x},{y}) published to RabbitMQ.")
                        # ADD THIS: Send confirmation to client
                        writer.write(f"COMMAND_RECEIVED MOVE\n".encode('utf-8')) # Already in English
                        logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: COMMAND_RECEIVED MOVE")
                        await writer.drain()
                    except ValueError:
                        writer.write("MOVE_ERROR Invalid coordinates\n".encode('utf-8')) # Already in English
                        logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: MOVE_ERROR Invalid coordinates")
                        await writer.drain()
                        logger.error(f"Invalid coordinates for MOVE command from {player.name}: {parts[1:]}")
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
                    logger.info(f"SHOOT command from {player.name} published to RabbitMQ.")
                    # ADD THIS: Send confirmation to client
                    writer.write(f"COMMAND_RECEIVED SHOOT\n".encode('utf-8')) # Already in English
                    logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: COMMAND_RECEIVED SHOOT")
                    await writer.drain()
            
            # Обработка других команд (например, из GameRoom.handle_player_command)
            elif player and cmd in ["SAY", "HELP", "PLAYERS", "QUIT"]:
                # Передаем команду в игровую комнату для обработки логики чата и информации
                await game_room.handle_player_command(player, message_str) # Responses are handled by game_room
                # Ответы игроку будут отправлены из game_room.handle_player_command через player.send_message
                # Если команда QUIT, то соединение будет закрыто там же.
                if cmd == "QUIT": # Если QUIT, то handle_player_command инициирует закрытие
                    logger.info(f"Player {player.name} sent QUIT. Connection will be closed.")
                    # Цикл прервется, когда writer закроется и readuntil вызовет исключение
            
            else: # Неизвестная команда
                logger.warning(f"Unknown command '{cmd}' from {player.name if player else addr}. Full message: '{message_str}'")
                # CHANGE THIS SECTION for UNKNOWN_COMMAND consistency
                # if player: 
                #     await player.send_message(f"SERVER: Unknown command '{cmd}'. Type HELP for a list of commands.")
                # else: 
                #     writer.write("UNKNOWN_COMMAND\n".encode('utf-8'))
                #     logger.debug(f"Attempting to drain writer for {addr} after sending: UNKNOWN_COMMAND")
                #     await writer.drain()
                # ALWAYS SEND UNKNOWN_COMMAND for simplicity in tests, or adjust tests
                writer.write("UNKNOWN_COMMAND\n".encode('utf-8')) # Already in English
                logger.debug(f"Attempting to drain writer for {player.name if player else addr} after sending: UNKNOWN_COMMAND")
                await writer.drain()

            # Подтверждение получения команды (если команда не QUIT и не вызвала ошибку ранее)
            # Этот ответ может быть избыточен, если game_room.handle_player_command уже отправил ответ.
            # Для MOVE/SHOOT ответ не обязателен, так как они асинхронны.
            if cmd not in ["QUIT", "LOGIN", "REGISTER"] and (cmd in ["MOVE", "SHOOT"] or player): # Только если это не команды, завершающие соединение или уже обработанные
                    # logger.info(f"DEBUG: Player {player.name if player else addr} is trying to send a response: {cmd.strip()}")
                # writer.write(f"COMMAND_RECEIVED {cmd}\n".encode('utf-8'))
                # await writer.drain()
                    # logger.info(f"DEBUG: Player {player.name if player else addr} response sent and flushed.")
                pass # Решено убрать общий COMMAND_RECEIVED, так как ответы специфичны для команд

    except ConnectionResetError:
        logger.warning(f"Connection reset by client {player.name if player else addr} ({addr}).", exc_info=True)
    except asyncio.IncompleteReadError:
        logger.warning(f"Client {player.name if player else addr} ({addr}) closed connection prematurely (IncompleteReadError).", exc_info=True)
    except Exception as e:
        logger.critical(f"Critical error in handle_game_client for {addr}: {e}", exc_info=True)
        if writer and not writer.is_closing(): # Если writer все еще открыт
            try:
                # Пытаемся уведомить клиента о критической ошибке
                writer.write(f"CRITICAL_SERVER_ERROR {type(e).__name__}\n".encode('utf-8')) # Already in English
                logger.debug(f"Attempting to drain writer for {addr} after sending: CRITICAL_SERVER_ERROR")
                await writer.drain()
            except Exception as we:
                logger.error(f"Failed to send critical error message to client {addr}: {we}")
    finally:
        logger.info(f"Finishing processing for {addr}. Player: {player.name if player else 'N/A'}.")
        if player: # Если объект игрока был создан
            logger.info(f"Removing player {player.name} from game room {game_room}.")
            await game_room.remove_player(player) # Удаляем игрока из игровой комнаты
        
        # Закрываем writer, если он еще не закрыт
        if writer and not writer.is_closing():
            logger.debug(f"Ensuring writer for {addr} is closed in finally block.")
            writer.close()
            try:
                await writer.wait_closed() # Ожидаем полного закрытия
            except Exception as e_close:
                logger.error(f"Error waiting for writer to close for {addr}: {e_close}", exc_info=True)
        logger.info(f"Connection with {addr} (player: {player.name if player else 'N/A'}) fully closed.")