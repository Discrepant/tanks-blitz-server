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
        
        message_str = data.decode()
        logger.debug(f"Получена UDP датаграмма от {addr}: '{message_str}'")

        try:
            message = json.loads(message_str)
            logger.debug(f"Декодированный JSON от {addr}: {message}")

            action = message.get("action")
            player_id = message.get("player_id") # Предполагаем, что ID игрока передается в каждом сообщении

            if not player_id:
                logger.warning(f"Нет player_id в сообщении от {addr}. Сообщение: '{message_str}'. Игнорируется.")
                return

            logger.info(f"Получено действие '{action}' от игрока '{player_id}' ({addr})")

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
                            if s_iter.get_players_count() < 2: # Пример: макс 2 игрока
                                target_session = s_iter
                                break
                        if not target_session:
                            target_session = self.session_manager.create_session()
                        
                        self.session_manager.add_player_to_session(target_session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": target_session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                        logger.info(f"Игрок {player_id} присоединился к сессии {target_session.session_id} с танком {tank.tank_id}")
                    else:
                        response = {"status": "join_failed", "reason": "No tanks available"}
                        logger.warning(f"Не удалось присоединить игрока {player_id}: нет свободных танков.")
                else:
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"Игрок {player_id} уже в сессии {session.session_id}.")
                
                if response:
                    self.transport.sendto(json.dumps(response).encode(), addr)
                    logger.debug(f"Отправлен ответ на join_game для {player_id} ({addr}): {response}")

            elif action == "move":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            new_position = message.get("position")
                            tank.move(tuple(new_position))
                            logger.debug(f"Танк {tank.tank_id} игрока {player_id} перемещен в {new_position}")
                            current_game_state = {"action": "game_update", "tanks": session.get_tanks_state()}
                            self.broadcast_to_session(session, current_game_state, f"game_update для игрока {player_id}")
                else:
                    logger.warning(f"Игрок {player_id} не в сессии, не может выполнить 'move'.")

            elif action == "shoot":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            tank.shoot() # Логика выстрела уже есть в методе tank.shoot()
                            logger.info(f"Танк {tank.tank_id} игрока {player_id} совершил выстрел.")
                            shoot_event = {"action": "player_shot", "player_id": player_id, "tank_id": tank.tank_id}
                            self.broadcast_to_session(session, shoot_event, f"player_shot от игрока {player_id}")
                else:
                    logger.warning(f"Игрок {player_id} не в сессии, не может выполнить 'shoot'.")
            
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
                        logger.info(f"Игрок {player_id} (Танк: {tank_id}) покинул игру. Танк возвращен в пул.")
                    if not self.session_manager.get_session(session.session_id): # Проверяем, была ли сессия удалена
                         logger.info(f"Сессия {session.session_id} была автоматически удалена (стала пустой).")
                else:
                    response = {"status": "not_in_game", "message": "You are not currently in a game."}
                    logger.warning(f"Игрок {player_id} пытался покинуть игру, но не был найден в активной сессии.")
                
                if response:
                    self.transport.sendto(json.dumps(response).encode(), addr)
                    logger.debug(f"Отправлен ответ на leave_game для {player_id} ({addr}): {response}")

            else:
                logger.warning(f"Неизвестное действие '{action}' от игрока {player_id} ({addr}). Сообщение: {message_str}")
                response = {"status": "error", "message": "Unknown action"}
                self.transport.sendto(json.dumps(response).encode(), addr)
                logger.debug(f"Отправлен ответ об ошибке (Unknown action) для {player_id} ({addr}): {response}")

        except json.JSONDecodeError:
            logger.error(f"Невалидный JSON получен от {addr}: '{message_str}'")
            self.transport.sendto(json.dumps({"status":"error", "message":"Invalid JSON format"}).encode(), addr)
        except Exception as e:
            logger.exception(f"Ошибка при обработке датаграммы от {addr} ({message_str}):")
            try:
                self.transport.sendto(json.dumps({"status":"error", "message":f"Internal server error: {type(e).__name__}"}).encode(), addr)
            except Exception as ex_send:
                logger.error(f"Не удалось отправить сообщение об ошибке клиенту {addr}: {ex_send}")

    def broadcast_to_session(self, session, message_dict, log_reason=""):
        message_bytes = json.dumps(message_dict).encode()
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
