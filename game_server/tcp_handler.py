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
# Импортируем метрики
from .metrics import GAME_CONNECTIONS, COMMANDS_PROCESSED, ERRORS_OCCURRED

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

CLIENT_TCP_READ_TIMEOUT = 30.0 # Таймаут для чтения команды от клиента (секунды)

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
    GAME_CONNECTIONS.labels(handler_type='tcp').inc() # Метрика: увеличиваем счетчик активных TCP соединений
    logger.debug(f"Handling new TCP connection from {addr}. Active TCP connections: {GAME_CONNECTIONS.labels(handler_type='tcp')._value}") # Обработка нового TCP-соединения от...

    # Отправка сообщения SERVER_ACK_CONNECTED
    logger.debug(f"Attempting to send SERVER_ACK_CONNECTED to {addr}")
    writer.write("СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n".encode('utf-8'))
    await writer.drain()
    logger.info(f"Successfully sent SERVER_ACK_CONNECTED to {addr}") # Успешно отправлено SERVER_ACK_CONNECTED...

    player: Player | None = None # Переменная для хранения объекта Player после успешного логина
    
    try:
        while True: # Основной цикл обработки команд от клиента
            logger.debug(f"TCPHandler [{addr}]: Waiting for command with timeout {CLIENT_TCP_READ_TIMEOUT}s...") # Ожидание команды с таймаутом...
            data = await asyncio.wait_for(reader.readuntil(b'\n'), timeout=CLIENT_TCP_READ_TIMEOUT)
            logger.debug(f"TCPHandler [{addr}]: Received raw data: {data!r}") # Получены сырые данные
            message_str = data.decode('utf-8').strip()
            logger.info(f"TCPHandler [{addr}]: Received command: '{message_str}'") # Получена команда (изменено с DEBUG на INFO для команд)
            
            if not message_str:
                logger.warning(f"TCPHandler [{addr}]: Empty command after strip from raw: {data!r}.") # Пустая команда после обработки из сырых данных
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='empty_command', status='error_format').inc()
                ERRORS_OCCURRED.labels(handler_type='tcp', error_type='empty_command').inc()
                writer.write("ПУСТАЯ_КОМАНДА\n".encode('utf-8')) # Отправляем ошибку клиенту
                logger.debug(f"Attempting to drain writer for {addr} after sending: EMPTY_COMMAND") # Попытка очистить буфер записи...
                await writer.drain()
                continue # Переходим к следующей итерации цикла

            parts = message_str.split() # Разделяем команду и аргументы
            if not parts: # Если после разделения ничего не осталось (маловероятно после strip, но для надежности)
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='empty_parts', status='error_format').inc()
                ERRORS_OCCURRED.labels(handler_type='tcp', error_type='empty_parts').inc()
                continue

            cmd = parts[0].upper() # Первое слово - команда, приводим к верхнему регистру
            
            # Обработка команды LOGIN
            if cmd == 'LOGIN' and len(parts) == 3:
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='LOGIN', status='received').inc()
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
                    response_msg = f"ВХОД_УСПЕШЕН {auth_message} Токен: {session_token if session_token else 'Н/Д'}\n"
                    logger.debug(f"GameTCPHandler: Sending LOGIN_SUCCESS to client. Message='{auth_message}', Token='{session_token if session_token else 'N/A'}'") # Отправка LOGIN_SUCCESS клиенту...
                    writer.write(response_msg.encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: LOGIN_SUCCESS") # Попытка очистить буфер записи...
                    await writer.drain()
                    logger.info(f"Player {username} logged in from {addr} (LOGIN_SUCCESS sent). Token: {session_token if session_token else 'N/A'}") # Игрок ... вошел в систему ... (LOGIN_SUCCESS отправлен)

                    # Теперь добавляем объект игрока в игровую комнату
                    # Это может отправить "Welcome" и другие сообщения комнаты
                    await game_room.add_player(player_obj)

                    # player_obj создается ПЕРЕД этим блоком tcp_handler
                    # Сообщение Welcome отправляется из game_room.add_player()
                    # Добавляем задержку *после* отправки сообщения welcome из add_player (или после LOGIN_SUCCESS)
                    await asyncio.sleep(0.02) # Увеличенная диагностическая задержка, пока оставлена
                else:
                    # Отправляем ответ о неудаче
                    response_msg = f"ВХОД_НЕУДАЧА {auth_message}\n"
                    logger.debug(f"GameTCPHandler: Sending LOGIN_FAILURE to client. Message='{auth_message}'") # Отправка LOGIN_FAILURE клиенту...
                    writer.write(response_msg.encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: LOGIN_FAILURE") # Попытка очистить буфер записи...
                    await writer.drain()
                    logger.info(f"Failed login for {username} from {addr}. Message: {auth_message}. Terminating handler.") # Неудачный вход для ... Завершение обработчика.
                    COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='LOGIN', status='auth_failed').inc()
                    ERRORS_OCCURRED.labels(handler_type='tcp', error_type='auth_failed').inc()
                    return  # Завершаем обработчик для этого клиента
            
            # Обработка команды REGISTER (заглушка)
            elif cmd == 'REGISTER' and len(parts) == 3:
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='REGISTER', status='rejected').inc()
                ERRORS_OCCURRED.labels(handler_type='tcp', error_type='registration_not_supported').inc()
                writer.write("РЕГИСТРАЦИЯ_НЕУДАЧА Регистрация через игровой сервер пока не поддерживается.\n".encode('utf-8'))
                logger.debug(f"Attempting to drain writer for {addr} after sending: REGISTER_FAILURE") # Попытка очистить буфер записи...
                await writer.drain()
                logger.info(f"REGISTER_FAILURE sent to {addr}. Terminating handler.") # REGISTER_FAILURE отправлен ... Завершение обработчика.
                return # Завершаем обработчик
            
            # Обработка команд MOVE или SHOOT
            elif cmd == 'MOVE' or cmd == 'SHOOT':
                if not player: # Если игрок не аутентифицирован
                    COMMANDS_PROCESSED.labels(handler_type='tcp', command_name=cmd, status='unauthorized').inc()
                    ERRORS_OCCURRED.labels(handler_type='tcp', error_type='unauthorized_command').inc()
                    writer.write("НЕ_АВТОРИЗОВАН Сначала вам нужно войти в систему\n".encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {addr} after sending: UNAUTHORIZED") # Попытка очистить буфер записи...
                    await writer.drain()
                    continue

                if cmd == 'MOVE':
                    if len(parts) < 3: # Проверяем наличие координат
                        COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='MOVE', status='error_format_coords_missing').inc()
                        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='move_coords_missing').inc()
                        writer.write("ОШИБКА_ДВИЖЕНИЯ Координаты отсутствуют\n".encode('utf-8'))
                        logger.debug(f"Attempting to drain writer for {addr} after sending: MOVE_ERROR Coordinates are missing") # Попытка очистить буфер записи...
                        await writer.drain()
                        continue
                    try:
                        x = int(parts[1]) # X координата
                        y = int(parts[2]) # Y координата
                        COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='MOVE', status='success').inc()
                        # Формируем данные команды для отправки в RabbitMQ
                        command_data = {
                            "player_id": player.name, # Используем имя игрока как ID
                            "command": "move",
                            "details": {"new_position": [x, y]}
                        }
                        # Публикуем команду в RabbitMQ
                        await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                        logger.info(f"MOVE command from {player.name} ({x},{y}) published to RabbitMQ.")
                        writer.write(f"КОМАНДА_ПОЛУЧЕНА MOVE\n".encode('utf-8'))
                        logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: COMMAND_RECEIVED MOVE") # Попытка очистить буфер записи...
                        await writer.drain()
                    except ValueError:
                        COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='MOVE', status='error_format_coords_invalid').inc()
                        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='move_coords_invalid').inc()
                        writer.write("ОШИБКА_ДВИЖЕНИЯ Неверные координаты\n".encode('utf-8'))
                        logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: MOVE_ERROR Invalid coordinates") # Попытка очистить буфер записи...
                        await writer.drain()
                        logger.error(f"Invalid coordinates for MOVE command from {player.name}: {parts[1:]}") # Неверные координаты для команды MOVE от...
                        continue
                elif cmd == 'SHOOT':
                    COMMANDS_PROCESSED.labels(handler_type='tcp', command_name='SHOOT', status='success').inc()
                    command_data = {
                        "player_id": player.name,
                        "command": "shoot",
                        "details": {"source": "tcp_handler"}
                    }
                    await publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_data)
                    logger.info(f"SHOOT command from {player.name} published to RabbitMQ.")
                    writer.write(f"КОМАНДА_ПОЛУЧЕНА SHOOT\n".encode('utf-8'))
                    logger.debug(f"Attempting to drain writer for {player.name} ({addr}) after sending: COMMAND_RECEIVED SHOOT") # Попытка очистить буфер записи...
                    await writer.drain()
            
            elif player and cmd in ["SAY", "HELP", "PLAYERS", "QUIT"]:
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name=cmd, status='delegated_to_gameroom').inc()
                await game_room.handle_player_command(player, message_str)
                if cmd == "QUIT":
                    logger.info(f"Player {player.name} sent QUIT. Connection will be closed.") # Игрок ... отправил QUIT. Соединение будет закрыто.
            
            else: # Неизвестная команда
                status_label = 'unknown_command_unauthenticated' if not player else 'unknown_command_authenticated'
                COMMANDS_PROCESSED.labels(handler_type='tcp', command_name=cmd if cmd else "no_command", status=status_label).inc()
                ERRORS_OCCURRED.labels(handler_type='tcp', error_type=status_label).inc()
                logger.warning(f"Unknown command '{cmd}' from {player.name if player else addr}. Full message: '{message_str}'") # Неизвестная команда ... от ...
                writer.write("НЕИЗВЕСТНАЯ_КОМАНДА\n".encode('utf-8'))
                logger.debug(f"Attempting to drain writer for {player.name if player else addr} after sending: UNKNOWN_COMMAND") # Попытка очистить буфер записи...
                await writer.drain()

            # Подтверждение получения команды (если команда не QUIT и не вызвала ошибку ранее)
            # Этот ответ может быть избыточен, если game_room.handle_player_command уже отправил ответ.
            # Для MOVE/SHOOT ответ не обязателен, так как они асинхронны.
            # pass # Решено убрать общий COMMAND_RECEIVED, так как ответы специфичны для команд

    except asyncio.TimeoutError:
        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='read_timeout').inc()
        logger.warning(f"TCPHandler [{addr}]: Timeout waiting for client command ({CLIENT_TCP_READ_TIMEOUT}s). Player: {player.name if player else 'N/A'}") # Таймаут ожидания команды клиента...
        if writer and not writer.is_closing():
            try:
                writer.write(f"ОШИБКА_СЕРВЕРА Таймаут ожидания команды\n".encode('utf-8'))
                await writer.drain()
            except Exception as e_timeout_send:
                logger.error(f"TCPHandler [{addr}]: Failed to send timeout error to client: {e_timeout_send}", exc_info=True) # Не удалось отправить ошибку таймаута клиенту
    except ConnectionResetError:
        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='connection_reset').inc()
        logger.warning(f"TCPHandler [{addr}]: Connection reset by client. Player: {player.name if player else 'N/A'}.", exc_info=True) # Соединение сброшено клиентом.
    except asyncio.IncompleteReadError:
        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='incomplete_read').inc()
        logger.warning(f"TCPHandler [{addr}]: Client closed connection prematurely (IncompleteReadError). Player: {player.name if player else 'N/A'}.", exc_info=True) # Клиент преждевременно закрыл соединение.
    except UnicodeDecodeError as ude:
        ERRORS_OCCURRED.labels(handler_type='tcp', error_type='unicode_decode_error').inc()
        logger.error(f"TCPHandler [{addr}]: Unicode decode error: {ude}. Raw data might not be UTF-8. Player: {player.name if player else 'N/A'}.", exc_info=True) # Ошибка декодирования Unicode...
        if writer and not writer.is_closing():
            try:
                writer.write("ОШИБКА_СЕРВЕРА Неверная кодировка символов. Ожидается UTF-8.\n".encode('utf-8'))
                await writer.drain()
            except Exception as ex_send:
                logger.error(f"TCPHandler [{addr}]: Failed to send UnicodeDecodeError response: {ex_send}", exc_info=True) # Не удалось отправить ответ об ошибке UnicodeDecodeError
    except Exception as e:
        ERRORS_OCCURRED.labels(handler_type='tcp', error_type=f'unhandled_exception_{type(e).__name__}').inc()
        logger.critical(f"TCPHandler [{addr}]: Critical error in handler. Player: {player.name if player else 'N/A'}: {e}", exc_info=True) # Критическая ошибка в обработчике.
        if writer and not writer.is_closing():
            try:
                writer.write(f"КРИТИЧЕСКАЯ_ОШИБКА_СЕРВЕРА {type(e).__name__}\n".encode('utf-8'))
                logger.debug(f"TCPHandler [{addr}]: Attempting to drain writer after sending: CRITICAL_SERVER_ERROR") # Попытка очистить буфер записи...
                await writer.drain()
            except Exception as we:
                logger.error(f"TCPHandler [{addr}]: Failed to send critical error message to client: {we}", exc_info=True) # Не удалось отправить критическое сообщение об ошибке клиенту
    finally:
        GAME_CONNECTIONS.labels(handler_type='tcp').dec() # Метрика: уменьшаем счетчик активных TCP соединений
        logger.info(f"TCPHandler [{addr}]: Starting finally block. Player: {player.name if player else 'N/A'}. Active TCP connections: {GAME_CONNECTIONS.labels(handler_type='tcp')._value}") # Запуск блока finally...
        
        if player:
            player_addr_info_finally = 'N/A (writer closed or None)' # Н/Д (writer закрыт или None)
            if player.writer and not player.writer.is_closing(): # Проверяем, можно ли использовать writer для get_extra_info
                try:
                    player_addr_info_finally = str(player.writer.get_extra_info('peername'))
                except Exception:  # pragma: no cover
                    player_addr_info_finally = 'N/A (error getting peername)' # Н/Д (ошибка получения peername)
            logger.info(f"TCP_HANDLER_FINALLY: Player {player.name} (ID: {player.id}, Addr: {player_addr_info_finally}). Attempting to remove from game room.") # Попытка удалить из игровой комнаты.
            await game_room.remove_player(player)
        else:
            # Используем addr напрямую, если объект player не существует
            logger.info(f"TCP_HANDLER_FINALLY: No player object to remove (likely connection error before login). Original Addr: {addr}") # Нет объекта игрока для удаления (вероятно, ошибка соединения до входа).

        if player and player.writer:
            if not player.writer.is_closing():
                logger.info(f"TCP_HANDLER_FINALLY: Player {player.name} (ID: {player.id}). Closing writer in finally block.") # Закрытие writer в блоке finally.
                player.writer.close()
                try:
                    await player.writer.wait_closed()
                except Exception as e_close:
                    logger.error(f"TCP_HANDLER_FINALLY: Player {player.name} (ID: {player.id}). Error waiting for writer to close: {e_close}", exc_info=True) # Ошибка ожидания закрытия writer.
            else:
                logger.info(f"TCP_HANDLER_FINALLY: Player {player.name} (ID: {player.id}). Writer was already closing in finally block.") # Writer уже закрывался в блоке finally.
        elif writer and not writer.is_closing(): # Запасной вариант, если player или player.writer равен None, но исходный writer существует
            logger.info(f"TCP_HANDLER_FINALLY: Original writer for {addr} exists. Closing it.") # Исходный writer для ... существует. Закрытие.
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_close:
                logger.error(f"TCP_HANDLER_FINALLY: Error waiting for original writer for {addr} to close: {e_close}", exc_info=True) # Ошибка ожидания закрытия исходного writer для ...

        logger.info(f"TCPHandler [{addr}]: Connection fully closed. Player: {player.name if player else 'N/A'}.") # Соединение полностью закрыто.