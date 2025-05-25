# game_server/session_manager.py
import uuid

class GameSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.players = {}  # {player_id: player_data} player_data может включать tank_id, адрес клиента и т.д.
        self.tanks = {} # {tank_id: tank_object} - танки, задействованные в этой сессии
        self.game_state = {} # Общее состояние игры для этой сессии
        print(f"GameSession {session_id} created.")

    def add_player(self, player_id, player_address, tank):
        if player_id in self.players:
            print(f"Player {player_id} already in session {self.session_id}.")
            return False
        self.players[player_id] = {'address': player_address, 'tank_id': tank.tank_id}
        self.tanks[tank.tank_id] = tank
        print(f"Player {player_id} (Tank: {tank.tank_id}) added to session {self.session_id} from address {player_address}.")
        return True

    def remove_player(self, player_id):
        player_data = self.players.pop(player_id, None)
        if player_data:
            tank_id_to_remove = player_data.get('tank_id')
            # Танк будет возвращен в пул отдельно, когда сессия закончится или игрок выйдет
            # self.tanks.pop(tank_id_to_remove, None) # Не удаляем здесь, чтобы не потерять ссылку если он еще нужен
            print(f"Player {player_id} removed from session {self.session_id}.")
        else:
            print(f"Player {player_id} not found in session {self.session_id}.")

    def get_all_player_addresses(self):
        return [p['address'] for p in self.players.values()]
    
    def get_players_count(self):
        return len(self.players)

    def get_tanks_state(self):
        """Собирает состояние всех танков в сессии."""
        return [tank.get_state() for tank in self.tanks.values()]


class SessionManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SessionManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'): # Гарантируем, что инициализация произойдет один раз
            self.sessions = {} # {session_id: GameSession_object}
            self.player_to_session = {} # {player_id: session_id} для быстрого поиска сессии игрока
            self.initialized = True
            print("SessionManager initialized.")

    def create_session(self):
        session_id = str(uuid.uuid4())
        session = GameSession(session_id)
        self.sessions[session_id] = session
        print(f"Session {session_id} created by SessionManager.")
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def remove_session(self, session_id):
        session = self.sessions.pop(session_id, None)
        if session:
            # Освободить всех игроков из этой сессии
            player_ids_in_session = list(session.players.keys()) # Копируем ключи, так как словарь будет изменяться
            for player_id in player_ids_in_session:
                self.player_to_session.pop(player_id, None)
                # Танки игроков из этой сессии должны быть возвращены в TankPool
                # Это будет сделано в логике завершения сессии или выхода игрока
            print(f"Session {session_id} removed by SessionManager.")
        return session

    def add_player_to_session(self, session_id, player_id, player_address, tank):
        session = self.get_session(session_id)
        if not session:
            print(f"Error: Session {session_id} not found.")
            return None
        if player_id in self.player_to_session:
            print(f"Error: Player {player_id} is already in session {self.player_to_session[player_id]}.")
            return None
        
        if session.add_player(player_id, player_address, tank):
            self.player_to_session[player_id] = session_id
            return session
        return None

    def remove_player_from_session(self, player_id):
        session_id = self.player_to_session.pop(player_id, None)
        if session_id:
            session = self.get_session(session_id)
            if session:
                session.remove_player(player_id)
                # Если в сессии не осталось игроков, ее можно удалить
                if session.get_players_count() == 0:
                    print(f"Session {session_id} is empty, removing.")
                    self.remove_session(session_id)
                return True
        print(f"Player {player_id} not found in any active session.")
        return False

    def get_session_by_player_id(self, player_id):
        session_id = self.player_to_session.get(player_id)
        if session_id:
            return self.get_session(session_id)
        return None

# Пример использования (для тестирования)
if __name__ == '__main__':
    from .tank_pool import TankPool # Предполагается, что tank_pool.py в том же каталоге

    sm1 = SessionManager()
    sm2 = SessionManager() # Тот же экземпляр
    print(f"SM1 is SM2: {sm1 is sm2}")

    tank_pool = TankPool(pool_size=2) # Нужен пул для танков

    # Создаем сессию
    session1 = sm1.create_session()
    
    player1_id = "player_A"
    player1_addr = ("127.0.0.1", 12345)
    tank1 = tank_pool.acquire_tank()

    player2_id = "player_B"
    player2_addr = ("127.0.0.1", 54321)
    tank2 = tank_pool.acquire_tank()
    
    if tank1:
        sm1.add_player_to_session(session1.session_id, player1_id, player1_addr, tank1)
    else:
        print("Failed to acquire tank for player_A")

    if tank2:
        sm1.add_player_to_session(session1.session_id, player2_id, player2_addr, tank2)
    else:
        print("Failed to acquire tank for player_B") # Если pool_size=1, это произойдет

    print(f"Session {session1.session_id} players: {session1.players}")
    
    retrieved_session = sm1.get_session_by_player_id(player1_id)
    if retrieved_session:
        print(f"Player {player1_id} is in session {retrieved_session.session_id}")

    sm1.remove_player_from_session(player1_id)
    if tank1: # Возвращаем танк в пул
        tank_pool.release_tank(tank1.tank_id)
    
    # Если последний игрок удален, сессия должна удалиться (проверяем по логам или состоянию sm1.sessions)
    sm1.remove_player_from_session(player2_id) 
    if tank2: # Возвращаем танк в пул
        tank_pool.release_tank(tank2.tank_id)

    print(f"Current sessions in SM: {sm1.sessions}")
