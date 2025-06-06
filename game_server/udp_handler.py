# game_server/udp_handler.py
# Этот модуль определяет класс GameUDPProtocol, который обрабатывает UDP-датаграммы
# от игровых клиентов. Используется для основного игрового взаимодействия,
# такого как движение, стрельба и обновление состояния игры.
import asyncio
import json
import logging # Добавляем импорт для логирования
from typing import Optional
from .session_manager import SessionManager, GameSession # Менеджер игровых сессий и GameSession
from .tank_pool import TankPool # Пул объектов танков
from .metrics import TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED # Метрики Prometheus
# Добавлен импорт для публикации команд в RabbitMQ
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS 

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

class GameUDPProtocol(asyncio.DatagramProtocol):
    """
    Протокол для обработки UDP-датаграмм игрового сервера.

    Отвечает за получение, декодирование, парсинг JSON-сообщений от клиентов,
    обработку игровых действий (присоединение, движение, стрельба, выход) и
    отправку ответов/обновлений состояния.
    """
    def __init__(self, session_manager: SessionManager, tank_pool: TankPool):
        """
        Инициализирует протокол с предоставленными экземплярами SessionManager и TankPool.
        """
        super().__init__()
        self.session_manager = session_manager
        self.tank_pool = tank_pool
        logger.info("GameUDPProtocol initialized with provided SessionManager and TankPool.")

    def connection_made(self, transport):
        """
        Вызывается при установке "соединения" (создании сокета).
        Сохраняет транспорт для последующей отправки данных.
        """
        self.transport = transport
        logger.info(f"UDP socket opened and listening on {transport.get_extra_info('sockname')}")

    def datagram_received(self, data: bytes, addr: tuple):
        """
        Вызывается при получении UDP-датаграммы.

        Обрабатывает входящие данные: декодирует, парсит JSON, выполняет действия
        в зависимости от содержимого сообщения (например, 'join_game', 'move', 'shoot').
        Обновляет метрики и отправляет ответы клиентам или широковещательные сообщения.

        Args:
            data (bytes): Полученные байты данных.
            addr (tuple): Адрес отправителя (IP, порт).
        """
        TOTAL_DATAGRAMS_RECEIVED.inc() # Увеличиваем счетчик полученных датаграмм
        logger.debug(f"UDP [{addr}]: Received raw datagram: {data!r}") # Consolidated raw data log

        decoded_payload_str = None # Will be used in exception log if other strings are not set

        try:
            # 1. Попытка декодирования (строгая)
            try:
                decoded_payload_str = data.decode('utf-8') # Строгое декодирование UTF-8
                logger.debug(f"UDP [{addr}]: Decoded message: '{decoded_payload_str.strip()}'") # Изменено на DEBUG для успешно декодированной строки перед разбором
            except UnicodeDecodeError as ude:
                logger.error(f"UDP [{addr}]: Unicode decode error: {ude}. Raw data: {data!r}", exc_info=True) # Ошибка декодирования Unicode...
                # Отправка ошибки клиенту
                self.transport.sendto(json.dumps({"status":"error", "message":"Неверная кодировка символов. Ожидается UTF-8."}).encode('utf-8'), addr)
                return

            # 2. Удаление пробельных символов
            processed_payload_str = decoded_payload_str.strip()
            
            # 3. Удаление нулевых символов (если есть)
            if '\x00' in processed_payload_str:
                cleaned_payload_str = processed_payload_str.replace('\x00', '')
                # Логируем, только если были внесены изменения, и используем очищенную строку
                if cleaned_payload_str != processed_payload_str:
                    logger.warning(f"Null bytes removed from data from {addr}. Original: '{processed_payload_str}', Cleaned: '{cleaned_payload_str}'") # Нулевые байты удалены из данных от...
                    processed_payload_str = cleaned_payload_str
            
            # 4. Проверка на пустоту после очистки
            if not processed_payload_str:
                logger.warning(f"UDP [{addr}]: Empty message after decoding, whitespace and null character cleaning. Original string: '{decoded_payload_str}', Original bytes: {data!r}") # Пустое сообщение после декодирования, очистки пробелов и нулевых символов.
                self.transport.sendto(json.dumps({"status": "error", "message": "Пустое JSON-сообщение"}).encode('utf-8'), addr)
                return

            logger.debug(f"UDP [{addr}]: Cleaned message for JSON parsing: '{processed_payload_str}'") # Очищенное сообщение для разбора JSON

            # 5. Попытка разбора JSON
            try:
                message = json.loads(processed_payload_str) # Разбор JSON
            except json.JSONDecodeError as jde:
                logger.error(f"UDP [{addr}]: Invalid JSON: '{processed_payload_str}'. Error: {jde}. Raw bytes: {data!r}", exc_info=True) # Неверный JSON...
                self.transport.sendto(json.dumps({"status":"error", "message":"Неверный формат JSON"}).encode('utf-8'), addr)
                return
            
            logger.debug(f"UDP [{addr}]: Successfully parsed JSON: {message}") # Успешно разобран JSON

            action = message.get("action")
            player_id = message.get("player_id")

            if not player_id:
                logger.warning(f"UDP [{addr}]: Missing player_id in message: {message}. Ignoring.") # Отсутствует player_id в сообщении... Игнорируется.
                # Нет ответа об ошибке для отсутствующего player_id, чтобы избежать усиления для некорректных/вредоносных UDP-пакетов
                return

            logger.info(f"UDP [{addr}]: Received action '{action}' from player '{player_id}'.") # Получено действие ... от игрока ...

            if action == "join_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if not session: # Если игрок еще не в сессии
                    tank = self.tank_pool.acquire_tank() # Пытаемся получить танк из пула
                    if tank:
                        TOTAL_PLAYERS_JOINED.inc() # Увеличиваем счетчик присоединившихся игроков
                        # Логика выбора или создания сессии
                        active_sessions_list = list(self.session_manager.sessions.values())
                        target_session = None
                        for s_iter in active_sessions_list:
                            if s_iter.get_players_count() < 2: # Пример: максимум 2 игрока в сессии
                                target_session = s_iter
                                break
                        if not target_session: # Если нет подходящей сессии, создаем новую
                            target_session = self.session_manager.create_session()
                        
                        self.session_manager.add_player_to_session(target_session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": target_session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                        logger.info(f"Player {player_id} joined session {target_session.session_id} with tank {tank.tank_id}")
                    else:
                        response = {"status": "join_failed", "reason": "Свободные танки отсутствуют"}
                        logger.warning(f"UDP [{addr}]: Failed to join player {player_id}: no free tanks.") # Не удалось присоединить игрока ... : нет свободных танков.
                else: # Если игрок уже в сессии
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"UDP [{addr}]: Player {player_id} is already in session {session.session_id}.") # Игрок ... уже в сессии ...
                
                if response: # Отправляем ответ клиенту
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"UDP [{addr}]: Sent response for join_game to player {player_id}: {response}") # Отправлен ответ для join_game игроку ...

            elif action == "move":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id')
                        if tank_id:
                            position = message.get("position")
                            if position:
                                command_message = {
                                    "player_id": player_id,
                                    "command": "move",
                                    "details": {
                                        "source": "udp_handler",
                                        "tank_id": tank_id,
                                        "new_position": position
                                    }
                                }
                                try:
                                    publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message) # Удален await
                                    logger.info(f"UDP [{addr}]: Published 'move' command for player {player_id} (tank: {tank_id}, position: {position}) to RabbitMQ.") # Опубликована команда 'move' для игрока ... в RabbitMQ.
                                except Exception as e:
                                    logger.error(f"UDP [{addr}]: Failed to publish 'move' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True) # Не удалось опубликовать команду 'move' ... в RabbitMQ
                            else:
                                logger.warning(f"UDP [{addr}]: Missing 'position' in 'move' command from player {player_id}. Message: {message}") # Отсутствует 'position' в команде 'move' от игрока ...
                        else:
                            logger.warning(f"UDP [{addr}]: tank_id not found for player {player_id} in session, cannot perform 'move'.") # tank_id не найден для игрока ... в сессии, невозможно выполнить 'move'.
                else:
                    logger.warning(f"UDP [{addr}]: Player {player_id} not in session, cannot perform 'move'.") # Игрок ... не в сессии, невозможно выполнить 'move'.

            elif action == "shoot":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id') # Получаем ID танка из данных игрока
                        if tank_id: # Проверяем, существует ли ID танка
                            # Существование танка будет проверено потребителем. Нам нужны только player_id и команда.
                            command_message = {
                                "player_id": player_id,
                                "command": "shoot",
                                "details": {
                                    "source": "udp_handler", # Источник команды
                                    "tank_id": tank_id # Включаем ID танка для удобного поиска потребителем
                                    # "timestamp": time.time() # Опционально: включаем временную метку клиента, если доступна и релевантна
                                }
                            }
                            try:
                                # Используем обменник по умолчанию (пустая строка), ключ маршрутизации - имя очереди
                                publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message) # Удален await
                                logger.info(f"UDP [{addr}]: Published 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ.") # Опубликована команда 'shoot' для игрока ... в RabbitMQ.
                            except Exception as e:
                                logger.error(f"UDP [{addr}]: Failed to publish 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True) # Не удалось опубликовать команду 'shoot' ... в RabbitMQ
                                # Опционально: отправка ошибки обратно игроку или обработка повторной попытки.
                        else:
                            logger.warning(f"UDP [{addr}]: tank_id not found for player {player_id} in session, cannot perform 'shoot'.") # tank_id не найден для игрока ... в сессии, невозможно выполнить 'shoot'.
                else:
                    logger.warning(f"UDP [{addr}]: Player {player_id} not in session, cannot perform 'shoot'.") # Игрок ... не в сессии, невозможно выполнить 'shoot'.
            
            elif action == "leave_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        self.session_manager.remove_player_from_session(player_id)
                        self.tank_pool.release_tank(tank_id)
                        response = {"status": "left_game", "message": "Вы покинули игру."}
                        logger.info(f"UDP [{addr}]: Player {player_id} (Tank: {tank_id}) left the game. Tank returned to pool.") # Игрок ... покинул игру. Танк возвращен в пул.
                    # Проверяем, была ли удалена сессия (если она стала пустой)
                    if not self.session_manager.get_session(session.session_id): # Проверяем, существует ли еще сессия
                         logger.info(f"UDP [{addr}]: Session {session.session_id} was automatically deleted after player {player_id} left (became empty).") # Сессия ... была автоматически удалена после выхода игрока ... (стала пустой).
                else: # Если игрок не найден в активной сессии
                    response = {"status": "not_in_game", "message": "Вы в данный момент не в игре."}
                    logger.warning(f"UDP [{addr}]: Player {player_id} tried to leave game but was not found in an active session.") # Игрок ... пытался покинуть игру, но не был найден в активной сессии.
                
                if response: # Отправляем ответ клиенту
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"UDP [{addr}]: Sent response for leave_game to player {player_id}: {response}") # Отправлен ответ для leave_game игроку ...

            else: # Неизвестное действие
                logger.warning(f"UDP [{addr}]: Unknown action '{action}' from player '{player_id}'. Message: {message}") # Неизвестное действие ... от игрока ...
                response = {"status": "error", "message": "Неизвестное действие"}
                self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                logger.debug(f"UDP [{addr}]: Sent error response (Unknown action) to player {player_id}: {response}") # Отправлен ответ об ошибке (Неизвестное действие) игроку ...

        except Exception as e: # Перехват всех других неожиданных ошибок во время обработки датаграммы
            msg_for_log = processed_payload_str if processed_payload_str is not None else \
                          (decoded_payload_str if decoded_payload_str is not None else f"Raw data: {data!r}") # Сырые данные
            logger.error(f"UDP [{addr}]: Error processing datagram (Processed/decoded data before error: '{msg_for_log}'): {e}", exc_info=True) # Ошибка обработки датаграммы (Обработанные/декодированные данные перед ошибкой: ...)
            try:
                self.transport.sendto(json.dumps({"status":"error", "message":f"Внутренняя ошибка сервера: {type(e).__name__}"}).encode('utf-8'), addr)
            except Exception as ex_send:
                logger.error(f"UDP [{addr}]: Failed to send generic error message to client: {ex_send}", exc_info=True) # Не удалось отправить общее сообщение об ошибке клиенту

    def broadcast_to_session(self, session: GameSession, message_dict: dict, log_reason: str = ""):
        """
        Sends a message to all players in the specified session.

        Args:
            session (GameSession): Session object whose players will receive the message.
            message_dict (dict): Dictionary with the message to send (will be serialized to JSON).
            log_reason (str, optional): Reason for broadcast for logging.
        """
        message_bytes = json.dumps(message_dict).encode('utf-8')
        logger.debug(f"UDP Broadcast to session {session.session_id} ({log_reason}): {message_dict}") # UDP-рассылка в сессию ... (причина): ...
        for player_id, player_info in session.players.items():
            player_addr = player_info['address']
            try:
                self.transport.sendto(message_bytes, player_addr)
                logger.debug(f"UDP Broadcast: Message ({log_reason}) successfully sent to player {player_id} at {player_addr}") # UDP-рассылка: Сообщение (...) успешно отправлено игроку ... по адресу ...
            except Exception as e:
                logger.error(f"UDP Broadcast: Error sending message to player {player_id} at {player_addr} in session {session.session_id}: {e}", exc_info=True) # UDP-рассылка: Ошибка отправки сообщения игроку ... в сессии ...
    
    def error_received(self, exc: Exception):
        """
        Called when a previous send or receive operation raises an OSError.
        Important for "connected" UDP sockets, less so for simple sendto/recvfrom.
        """
        logger.error(f"UDP socket error received: {exc}", exc_info=True) # Получена ошибка UDP-сокета

    def connection_lost(self, exc: Optional[Exception]):
        """
        Called when the "connection" is lost.
        For datagram protocols, this usually means the socket was closed.
        """
        # This method is called for some "connected" UDP sockets, but not for regular ones.
        # In our case, create_datagram_endpoint creates a listening socket, it doesn't "lose" a connection by itself.
        # Этот метод вызывается для некоторых "подключенных" UDP-сокетов, но не для обычных.
        # В нашем случае create_datagram_endpoint создает слушающий сокет, он сам по себе не "теряет" соединение.
        if exc:
            logger.error(f"UDP socket closed with error: {exc}") # UDP-сокет закрыт с ошибкой
        else:
            logger.info("UDP socket closed.") # UDP-сокет закрыт.
