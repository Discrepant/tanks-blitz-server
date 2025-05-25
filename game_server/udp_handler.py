# game_server/udp_handler.py
import asyncio
import json
from .session_manager import SessionManager
from .tank_pool import TankPool
# Импортируем метрики из game_server.main (или где они определены)
# Это создаст циклическую зависимость, если метрики в main, а main импортирует udp_handler.
# Лучше вынести определение метрик в отдельный файл, например, game_server/metrics.py
# Пока для простоты оставим так, но это нужно будет исправить.
# Предположим, что мы импортируем их из metrics.py, который нужно будет создать.
# from .metrics import TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED, ACTIVE_SESSIONS, TANKS_IN_USE

# Вместо этого, передадим функции обновления метрик в конструктор или будем использовать глобальные объекты из main
from .main import TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED, ACTIVE_SESSIONS, TANKS_IN_USE, update_metrics


class GameUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        super().__init__()
        self.session_manager = SessionManager()
        self.tank_pool = TankPool()
        print("GameUDPProtocol initialized.")

    def connection_made(self, transport):
        self.transport = transport
        print("UDP Connection (socket) opened.")

    def datagram_received(self, data, addr):
        TOTAL_DATAGRAMS_RECEIVED.inc() # Увеличиваем счетчик полученных датаграмм
        # update_metrics() # Обновляем Gauge метрики после каждого события - main.py это делает в цикле

        message_str = data.decode()
        # print(f"Received UDP packet from {addr}: {message_str}") # Уже логируется в udp_handler

        # Полный код datagram_received с инкрементами:
        try:
            message = json.loads(message_str)
            action = message.get("action")
            player_id = message.get("player_id")

            if not player_id:
                print(f"No player_id in message from {addr}. Ignoring.")
                return

            if action == "join_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                if not session:
                    tank = self.tank_pool.acquire_tank()
                    if tank:
                        TOTAL_PLAYERS_JOINED.inc() # Инкремент здесь
                        active_sessions_list = list(self.session_manager.sessions.values())
                        # Упрощенная логика выбора/создания сессии
                        if not active_sessions_list or active_sessions_list[0].get_players_count() >= 2: # Пример: макс 2 игрока
                            session = self.session_manager.create_session()
                        else:
                            session = active_sessions_list[0]
                        
                        self.session_manager.add_player_to_session(session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                    else:
                        response = {"status": "join_failed", "reason": "No tanks available"}
                else:
                    response = {"status": "already_in_session", "session_id": session.session_id}
                self.transport.sendto(json.dumps(response).encode(), addr)

            elif action == "move":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            new_position = message.get("position")
                            tank.move(tuple(new_position))
                            current_game_state = {"action": "game_update", "tanks": session.get_tanks_state()}
                            self.broadcast_to_session(session, current_game_state)
                else:
                    print(f"Player {player_id} not in a session, cannot move.") # Логируем, если игрок не в сессии

            elif action == "shoot":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            tank.shoot()
                            shoot_event = {"action": "player_shot", "player_id": player_id, "tank_id": tank.tank_id}
                            self.broadcast_to_session(session, shoot_event)
                else:
                    print(f"Player {player_id} not in a session, cannot shoot.") # Логируем
            
            elif action == "leave_game":
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        self.session_manager.remove_player_from_session(player_id)
                        self.tank_pool.release_tank(tank_id)
                        # TOTAL_PLAYERS_LEFT.inc() # Можно добавить такую метрику, если нужно
                        response = {"status": "left_game", "message": "You have left the game."}
                        self.transport.sendto(json.dumps(response).encode(), addr)
                        print(f"Player {player_id} (Tank: {tank_id}) left game and tank released.")
                    # SessionManager.remove_player_from_session должен сам удалить сессию, если она пуста
                    if not self.session_manager.get_session(session.session_id): # Проверяем, была ли сессия удалена
                         print(f"Session {session.session_id} was automatically removed as it became empty.")
                else:
                    response = {"status": "not_in_game", "message": "You are not currently in a game."}
                    self.transport.sendto(json.dumps(response).encode(), addr)
            else:
                print(f"Unknown action: {action} from {addr}")
                response = {"status": "error", "message": "Unknown action"}
                self.transport.sendto(json.dumps(response).encode(), addr)

        except json.JSONDecodeError:
            print(f"Invalid JSON received from {addr}: {message_str}")
            self.transport.sendto(json.dumps({"status":"error", "message":"Invalid JSON format"}).encode(), addr)
        except Exception as e:
            print(f"Error processing datagram from {addr}: {e}")
            self.transport.sendto(json.dumps({"status":"error", "message":str(e)}).encode(), addr)
        finally:
            # Обновляем Gauge метрики (ACTIVE_SESSIONS, TANKS_IN_USE)
            # Это будет вызвано из metrics_updater_loop в main.py,
            # но для более быстрой реакции на изменения (например, после join/leave) можно вызвать и здесь.
            # Однако, это может привести к частым вызовам, если datagram_received вызывается часто.
            # Оставим обновление Gauge на metrics_updater_loop в main.py для периодичности.
            # update_metrics() # Убрано, так как обновление Gauge идет из цикла в main.py
            pass


    def broadcast_to_session(self, session, message_dict):
        message_bytes = json.dumps(message_dict).encode()
        for player_info in session.players.values():
            player_addr = player_info['address']
            try:
                self.transport.sendto(message_bytes, player_addr)
            except Exception as e:
                print(f"Error broadcasting to {player_addr}: {e}")
    
    def connection_lost(self, exc):
        print("UDP Socket closed.")
