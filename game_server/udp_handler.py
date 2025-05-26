# game_server/udp_handler.py
import asyncio
import json
import logging # Добавляем импорт
from .session_manager import SessionManager
from .tank_pool import TankPool
from .metrics import TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

class GameUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        super().__init__()
        self.session_manager = SessionManager()
        self.tank_pool = TankPool()
        logger.info("GameUDPProtocol initialized.")

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"UDP cокет открыт и слушает на {transport.get_extra_info('sockname')}")

    def datagram_received(self, data, addr):
        TOTAL_DATAGRAMS_RECEIVED.inc()
        # logger.debug(f"Raw bytes received: {data}") # Moved down after initial try

        decoded_payload_str = None # To be used in the final exception log if other strings are not set

        try:
            logger.debug(f"Raw bytes received from {addr}: {data!r}") # Log original bytes
            # 1. Attempt to decode (strictly)
            try:
                decoded_payload_str = data.decode('utf-8') # Strict decoding
            except UnicodeDecodeError as ude:
                logger.error(f"Unicode decoding error from {addr}: {ude}. Raw data: {data!r}")
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid character encoding. UTF-8 expected."}).encode('utf-8'), addr)
                return

            # 2. Strip whitespace
            processed_payload_str = decoded_payload_str.strip()
            
            # 3. Null character removal
            if '\x00' in processed_payload_str:
                cleaned_payload_str = processed_payload_str.replace('\x00', '')
                # Log only if changes were made, and use the cleaned string
                if cleaned_payload_str != processed_payload_str:
                    logger.warning(f"Removed null characters from data from {addr}. Original: '{processed_payload_str}', Cleaned: '{cleaned_payload_str}'")
                    processed_payload_str = cleaned_payload_str
            
            # 4. Check if empty after stripping and cleaning
            if not processed_payload_str:
                logger.warning(f"Empty message after decoding, stripping, and cleaning from {addr}. Original string: '{decoded_payload_str}', Original bytes: {data!r}")
                self.transport.sendto(json.dumps({"status": "error", "message": "Empty JSON payload"}).encode('utf-8'), addr)
                return

            logger.debug(f"Successfully decoded, stripped, and cleaned message from {addr}: '{processed_payload_str}'")

            # 5. Attempt to parse JSON
            try:
                message = json.loads(processed_payload_str)
            except json.JSONDecodeError as jde:
                # Log with the string that failed parsing and the original bytes
                logger.error(f"Invalid JSON received from {addr}: '{processed_payload_str}' | Error: {jde}. Raw bytes: {data!r}")
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid JSON format"}).encode('utf-8'), addr)
                return
            
            # If parsing is successful, log the JSON object
            logger.debug(f"Successfully parsed JSON from {addr}: {message}")

            # Main message processing logic starts here
            action = message.get("action")
            player_id = message.get("player_id")

            if not player_id:
                logger.warning(f"No player_id in message from {addr}. Message: '{processed_payload_str}'. Ignoring.")
                return

            logger.info(f"Received action '{action}' from player '{player_id}' ({addr})")

            if action == "join_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if not session:
                    tank = self.tank_pool.acquire_tank()
                    if tank:
                        TOTAL_PLAYERS_JOINED.inc()
                        active_sessions_list = list(self.session_manager.sessions.values())
                        target_session = None
                        for s_iter in active_sessions_list:
                            if s_iter.get_players_count() < 2: # Example: max 2 players
                                target_session = s_iter
                                break
                        if not target_session:
                            target_session = self.session_manager.create_session()
                        
                        self.session_manager.add_player_to_session(target_session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": target_session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                        logger.info(f"Player {player_id} joined session {target_session.session_id} with tank {tank.tank_id}")
                    else:
                        response = {"status": "join_failed", "reason": "No tanks available"}
                        logger.warning(f"Failed to join player {player_id}: no tanks available.")
                else:
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"Player {player_id} is already in session {session.session_id}.")
                
                if response:
                    self.transport.sendto(json.dumps(response).encode(), addr)
                    logger.debug(f"Sent response for join_game to {player_id} ({addr}): {response}")

            elif action == "move":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            new_position = message.get("position")
                            tank.move(tuple(new_position)) # Ensure position is a tuple
                            logger.debug(f"Tank {tank.tank_id} of player {player_id} moved to {new_position}")
                            current_game_state = {"action": "game_update", "tanks": session.get_tanks_state()}
                            self.broadcast_to_session(session, current_game_state, f"game_update for player {player_id}")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'move'.")

            elif action == "shoot":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            tank.shoot()
                            logger.info(f"Tank {tank.tank_id} of player {player_id} fired a shot.")
                            shoot_event = {"action": "player_shot", "player_id": player_id, "tank_id": tank.tank_id}
                            self.broadcast_to_session(session, shoot_event, f"player_shot from player {player_id}")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'shoot'.")
            
            elif action == "leave_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        self.session_manager.remove_player_from_session(player_id)
                        self.tank_pool.release_tank(tank_id)
                        response = {"status": "left_game", "message": "You have left the game."}
                        logger.info(f"Player {player_id} (Tank: {tank_id}) left the game. Tank returned to pool.")
                    if not self.session_manager.get_session(session.session_id):
                         logger.info(f"Session {session.session_id} was automatically deleted (became empty).")
                else:
                    response = {"status": "not_in_game", "message": "You are not currently in a game."}
                    logger.warning(f"Player {player_id} tried to leave game but was not found in an active session.")
                
                if response:
                    self.transport.sendto(json.dumps(response).encode(), addr)
                    logger.debug(f"Sent response for leave_game to {player_id} ({addr}): {response}")

            else:
                logger.warning(f"Unknown action '{action}' from player {player_id} ({addr}). Message: {processed_payload_str}")
                response = {"status": "error", "message": "Unknown action"}
                self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                logger.debug(f"Sent error response (Unknown action) to {player_id} ({addr}): {response}")

        except Exception as e:
            # Use processed_payload_str if available, otherwise decoded_payload_str, else log raw data
            msg_for_log = processed_payload_str if processed_payload_str is not None else \
                          (decoded_payload_str if decoded_payload_str is not None else f"Raw data: {data!r}")
            logger.exception(f"Error processing datagram from {addr} (Processed/decoded data before error: '{msg_for_log}'):")
            try:
                self.transport.sendto(json.dumps({"status":"error", "message":f"Internal server error: {type(e).__name__}"}).encode('utf-8'), addr)
            except Exception as ex_send:
                logger.error(f"Не удалось отправить сообщение об ошибке клиенту {addr}: {ex_send}")

    def broadcast_to_session(self, session, message_dict, log_reason=""):
        message_bytes = json.dumps(message_dict).encode('utf-8') # Ensure UTF-8 for sending
        # Логируем само сообщение только на DEBUG уровне, чтобы не засорять логи при частых обновлениях
        logger.debug(f"Широковещательное сообщение для сессии {session.session_id} ({log_reason}): {message_dict}")
        for player_id, player_info in session.players.items():
            player_addr = player_info['address']
            try:
                self.transport.sendto(message_bytes, player_addr)
                logger.debug(f"Сообщение ({log_reason}) отправлено игроку {player_id} на {player_addr}")
            except Exception as e:
                logger.error(f"Ошибка при широковещательной отправке игроку {player_id} на {player_addr}: {e}")
    
    def connection_lost(self, exc):
        # Этот метод вызывается для некоторых "связанных" UDP сокетов, но не для обычных.
        # В нашем случае create_datagram_endpoint создает слушающий сокет, он не "теряет" соединение сам по себе.
        if exc:
            logger.error(f"UDP сокет закрыт с ошибкой: {exc}")
        else:
            logger.info("UDP сокет закрыт.")
