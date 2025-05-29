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
    def __init__(self):
        """
        Инициализирует протокол, получая экземпляры SessionManager и TankPool.
        Предполагается, что SessionManager и TankPool реализованы как Singletons.
        """
        super().__init__()
        self.session_manager = SessionManager() # Получаем экземпляр менеджера сессий
        self.tank_pool = TankPool() # Получаем экземпляр пула танков
        logger.info("GameUDPProtocol initialized.")

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
        logger.info(f"UDP Handler: Raw request received from {addr}: {data!r}")
        TOTAL_DATAGRAMS_RECEIVED.inc() # Увеличиваем счетчик полученных датаграмм
        # logger.debug(f"Raw bytes received: {data}") # Moved lower, after first processing attempt

        decoded_payload_str = None # Will be used in exception log if other strings are not set

        try:
            logger.debug(f"Raw bytes received from {addr}: {data!r}") # Log original bytes

            # 1. Attempt decoding (strict)
            try:
                decoded_payload_str = data.decode('utf-8') # Strict UTF-8 decoding
                logger.info(f"UDP Handler: Decoded message from {addr}: {decoded_payload_str.strip()}")
            except UnicodeDecodeError as ude:
                logger.error(f"Unicode decode error from {addr}: {ude}. Raw data: {data!r}")
                # Send error to client
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid character encoding. UTF-8 expected."}).encode('utf-8'), addr) # Already in English
                return

            # 2. Remove whitespace
            processed_payload_str = decoded_payload_str.strip()
            
            # 3. Remove null characters (if any)
            if '\x00' in processed_payload_str:
                cleaned_payload_str = processed_payload_str.replace('\x00', '')
                # Log only if changes were made, and use the cleaned string
                if cleaned_payload_str != processed_payload_str:
                    logger.warning(f"Null bytes removed from data from {addr}. Original: '{processed_payload_str}', Cleaned: '{cleaned_payload_str}'")
                    processed_payload_str = cleaned_payload_str
            
            # 4. Check for emptiness after cleaning
            if not processed_payload_str:
                logger.warning(f"Empty message after decoding, whitespace and null character cleaning from {addr}. Original string: '{decoded_payload_str}', Original bytes: {data!r}")
                self.transport.sendto(json.dumps({"status": "error", "message": "Empty JSON message"}).encode('utf-8'), addr) # Already in English
                return

            logger.debug(f"Successfully decoded, cleaned (whitespace, nulls) message from {addr}: '{processed_payload_str}'")

            # 5. Attempt JSON parsing
            try:
                message = json.loads(processed_payload_str) # Parse JSON
            except json.JSONDecodeError as jde:
                # Log the string that failed to parse, and original bytes
                logger.error(f"Invalid JSON received from {addr}: '{processed_payload_str}' | Error: {jde}. Raw bytes: {data!r}")
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid JSON format"}).encode('utf-8'), addr) # Already in English
                return
            
            # If parsing is successful, log the JSON object
            logger.debug(f"Successfully parsed JSON from {addr}: {message}")

            # Main message processing logic starts here
            action = message.get("action") # Action the client wants to perform
            player_id = message.get("player_id") # Player ID

            if not player_id: # If player ID is missing
                logger.warning(f"Missing player_id in message from {addr}. Message: '{processed_payload_str}'. Ignoring.")
                # Can send an error, but for UDP this might be excessive if no response is expected.
                return

            logger.info(f"Received action '{action}' from player '{player_id}' ({addr})")

            if action == "join_game": # Join game
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
                        response = {"status": "join_failed", "reason": "No free tanks available"}
                        logger.warning(f"Failed to join player {player_id}: no free tanks.")
                else: # If player is already in session
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"Player {player_id} is already in session {session.session_id}.")
                
                if response: # Send response to client
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Sent response for join_game to player {player_id} ({addr}): {response}")

            elif action == "move": # Tank movement
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
                                    publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message)
                                    logger.info(f"Published 'move' command for player {player_id} (tank: {tank_id}, position: {position}) to RabbitMQ queue '{RABBITMQ_QUEUE_PLAYER_COMMANDS}'.")
                                except Exception as e:
                                    logger.error(f"Failed to publish 'move' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True)
                            else:
                                logger.warning(f"Missing 'position' in 'move' command from player {player_id} ({addr}).")
                        else:
                            logger.warning(f"tank_id not found for player {player_id} in session, cannot perform 'move'.")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'move'.")

            elif action == "shoot": # Tank shot
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id') # Get tank ID from player data
                        if tank_id: # Check if tank ID exists
                            # Tank existence will be checked by the consumer. We only need player_id and command.
                            command_message = {
                                "player_id": player_id,
                                "command": "shoot",
                                "details": {
                                    "source": "udp_handler", # Command source
                                    "tank_id": tank_id # Include tank ID for easy lookup by consumer
                                    # "timestamp": time.time() # Optionally: include client timestamp if available and relevant
                                }
                            }
                            try:
                                # Use default exchange (empty string), routing key is queue name
                                publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message)
                                logger.info(f"Published 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ queue '{RABBITMQ_QUEUE_PLAYER_COMMANDS}'.")
                            except Exception as e:
                                logger.error(f"Failed to publish 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True)
                                # Optionally: send error back to player or handle retry.
                                # For now, just log the error.

                            # Removed direct call to tank.shoot() and broadcast_to_session for shot event.
                            # Consumer is now responsible for processing the command and any resulting game state updates/broadcasts.
                            # Optimistic update can be sent here if needed, but task assumes consumer handles this.
                            # Example: self.transport.sendto(json.dumps({"status":"shoot_command_sent"}).encode('utf-8'), addr)
                        else:
                            logger.warning(f"tank_id not found for player {player_id} in session, cannot perform 'shoot'.")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'shoot'.")
            
            elif action == "leave_game": # Leave game
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        self.session_manager.remove_player_from_session(player_id) # Remove player from session
                        self.tank_pool.release_tank(tank_id) # Return tank to pool
                        response = {"status": "left_game", "message": "You have left the game."} # Already in English
                        logger.info(f"Player {player_id} (Tank: {tank_id}) left the game. Tank returned to pool.")
                    # Check if session was deleted (if it became empty)
                    if not self.session_manager.get_session(session.session_id):
                         logger.info(f"Session {session.session_id} was automatically deleted (became empty).")
                else: # If player not found in active session
                    response = {"status": "not_in_game", "message": "You are not currently in a game."} # Already in English
                    logger.warning(f"Player {player_id} tried to leave game but was not found in an active session.")
                
                if response: # Send response to client
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Sent response for leave_game to player {player_id} ({addr}): {response}")

            else: # Unknown action
                logger.warning(f"Unknown action '{action}' from player {player_id} ({addr}). Message: {processed_payload_str}")
                response = {"status": "error", "message": "Unknown action"} # Already in English
                self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                logger.debug(f"Sent error response (Unknown action) to player {player_id} ({addr}): {response}")

        except Exception as e:
            # Use processed_payload_str if available, otherwise decoded_payload_str, otherwise log raw data
            msg_for_log = processed_payload_str if processed_payload_str is not None else \
                          (decoded_payload_str if decoded_payload_str is not None else f"Raw data: {data!r}")
            logger.exception(f"Error processing datagram from {addr} (Processed/decoded data before error: '{msg_for_log}'):")
            try:
                # Try to send a generic error message to the client
                self.transport.sendto(json.dumps({"status":"error", "message":f"Internal server error: {type(e).__name__}"}).encode('utf-8'), addr) # Already in English
            except Exception as ex_send:
                logger.error(f"Failed to send error message to client {addr}: {ex_send}")

    def broadcast_to_session(self, session: GameSession, message_dict: dict, log_reason: str = ""):
        """
        Sends a message to all players in the specified session.

        Args:
            session (GameSession): Session object whose players will receive the message.
            message_dict (dict): Dictionary with the message to send (will be serialized to JSON).
            log_reason (str, optional): Reason for broadcast for logging.
        """
        message_bytes = json.dumps(message_dict).encode('utf-8') # Ensure UTF-8 is used
        # Log the message itself only at DEBUG level to avoid cluttering logs during frequent updates
        logger.debug(f"Broadcasting message to session {session.session_id} ({log_reason}): {message_dict}")
        for player_id, player_info in session.players.items(): # Iterate over players in session
            player_addr = player_info['address'] # Get player address
            try:
                self.transport.sendto(message_bytes, player_addr) # Send message
                logger.debug(f"Message ({log_reason}) sent to player {player_id} at {player_addr}")
            except Exception as e:
                logger.error(f"Error broadcasting message to player {player_id} at {player_addr}: {e}")
    
    def connection_lost(self, exc: Optional[Exception]):
        """
        Called when the "connection" is lost.
        For datagram protocols, this usually means the socket was closed.
        """
        # This method is called for some "connected" UDP sockets, but not for regular ones.
        # In our case, create_datagram_endpoint creates a listening socket, it doesn't "lose" a connection by itself.
        if exc:
            logger.error(f"UDP socket closed with error: {exc}")
        else:
            logger.info("UDP socket closed.")
