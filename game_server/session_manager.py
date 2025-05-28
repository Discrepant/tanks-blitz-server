# game_server/session_manager.py
# Этот модуль определяет классы GameSession и SessionManager для управления
# игровыми сессиями и игроками в них. SessionManager реализован как Singleton.
import uuid # Для генерации уникальных ID сессий
import time # Для временных меток событий
from core.message_broker_clients import send_kafka_message, KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS
import logging # Добавляем логирование

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

class GameSession:
    """
    Представляет одну игровую сессию (или "комнату").

    Содержит информацию об игроках в сессии, их танках и общем состоянии игры.

    Атрибуты:
        session_id (str): Уникальный идентификатор сессии.
        players (dict): Словарь игроков в сессии. 
                        Ключ - ID игрока, значение - словарь с данными игрока
                        (например, 'address', 'tank_id').
        tanks (dict): Словарь объектов танков, задействованных в этой сессии.
                      Ключ - ID танка, значение - объект танка.
        game_state (dict): Словарь, представляющий общее состояние игры для этой сессии.
                           Может содержать информацию о счете, времени раунда и т.д.
    """
    def __init__(self, session_id):
        """
        Инициализирует игровую сессию.

        Args:
            session_id (str): Уникальный идентификатор для этой сессии.
        """
        self.session_id = session_id
        # players: {player_id: {'address': player_address, 'tank_id': tank.tank_id}}
        self.players = {}  
        # tanks: {tank_id: tank_object}
        self.tanks = {} 
        self.game_state = {} # Общее состояние игры для этой сессии
        logger.info(f"Game session {session_id} created.")

    def add_player(self, player_id, player_address, tank):
        """
        Добавляет игрока в сессию.

        Args:
            player_id (any): Уникальный идентификатор игрока.
            player_address (any): Сетевой адрес игрока (например, для UDP).
            tank (Tank): Объект танка, назначенный игроку.

        Returns:
            bool: True, если игрок успешно добавлен, False, если игрок уже в сессии.
        """
        if player_id in self.players:
            logger.warning(f"Player {player_id} is already in session {self.session_id}.")
            return False
        # Сохраняем данные игрока, включая ID его танка и адрес
        self.players[player_id] = {'address': player_address, 'tank_id': tank.tank_id}
        # Сохраняем сам объект танка
        self.tanks[tank.tank_id] = tank
        logger.info(f"Player {player_id} (Tank: {tank.tank_id}) added to session {self.session_id} from address {player_address}.")
        return True

    def remove_player(self, player_id):
        """
        Удаляет игрока из сессии.

        Примечание: Танк игрока не возвращается в пул здесь, это должно
        обрабатываться отдельно (например, SessionManager при выходе игрока
        или завершении сессии).

        Args:
            player_id (any): Идентификатор игрока для удаления.
        """
        player_data = self.players.pop(player_id, None)
        if player_data:
            tank_id_to_remove = player_data.get('tank_id')
            # Не удаляем танк из self.tanks здесь, так как он может быть еще нужен
            # для отправки последнего состояния или других операций перед возвратом в пул.
            # Возврат танка в пул - ответственность SessionManager или TankPool.
            logger.info(f"Player {player_id} (Tank: {tank_id_to_remove}) removed from session {self.session_id}.")
        else:
            logger.warning(f"Player {player_id} not found in session {self.session_id} during removal attempt.")

    def get_all_player_addresses(self):
        """
        Возвращает список всех адресов игроков в сессии.
        Это может быть полезно для рассылки UDP-сообщений всем участникам.
        """
        return [p_data['address'] for p_data in self.players.values() if 'address' in p_data]
    
    def get_players_count(self):
        """Возвращает текущее количество игроков в сессии."""
        return len(self.players)

    def get_tanks_state(self):
        """
        Собирает и возвращает состояние всех танков в сессии.
        Предполагается, что у объектов танков есть метод `get_state()`.
        """
        return [tank.get_state() for tank in self.tanks.values()]


class SessionManager:
    """
    Управляет активными игровыми сессиями. Реализован как Singleton.

    Отвечает за создание, получение, удаление сессий, а также за добавление
    и удаление игроков из сессий. Отправляет события о жизненном цикле сессий
    и игроков в Kafka.

    Атрибуты:
        sessions (dict): Словарь активных сессий. Ключ - ID сессии, значение - объект GameSession.
        player_to_session (dict): Словарь для быстрого поиска сессии по ID игрока.
                                  Ключ - ID игрока, значение - ID сессии.
    """
    _instance = None # Экземпляр Singleton

    def __new__(cls, *args, **kwargs):
        """ Реализация паттерна Singleton. """
        if not cls._instance:
            cls._instance = super(SessionManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        Инициализирует SessionManager. Гарантирует однократную инициализацию.
        """
        if not hasattr(self, 'initialized'): # Гарантируем, что инициализация произойдет один раз
            self.sessions = {} # {session_id: GameSession_object}
            self.player_to_session = {} # {player_id: session_id} для быстрого поиска
            self.initialized = True
            logger.info("SessionManager initialized.")

    def create_session(self):
        """
        Создает новую игровую сессию с уникальным ID.

        Отправляет событие 'session_created' в Kafka.

        Returns:
            GameSession: Созданный объект игровой сессии.
        """
        session_id = str(uuid.uuid4()) # Генерируем уникальный ID для сессии
        session = GameSession(session_id)
        self.sessions[session_id] = session
        logger.info(f"Session {session_id} created by session manager.")
        
        # Отправляем сообщение в Kafka о создании сессии
        kafka_message = {
            "event_type": "session_created",
            "session_id": session_id,
            "timestamp": time.time() # Временная метка создания
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, kafka_message)
        return session

    def get_session(self, session_id):
        """
        Возвращает объект сессии по ее ID.

        Args:
            session_id (str): Идентификатор сессии.

        Returns:
            GameSession | None: Объект сессии, если найден, иначе None.
        """
        return self.sessions.get(session_id)

    def remove_session(self, session_id, reason="explicitly_removed"):
        """
        Удаляет сессию по ее ID.

        Отправляет событие 'session_removed' в Kafka с указанием причины.
        Также удаляет всех игроков этой сессии из маппинга `player_to_session`.

        Args:
            session_id (str): Идентификатор сессии для удаления.
            reason (str, optional): Причина удаления сессии. По умолчанию "explicitly_removed".

        Returns:
            GameSession | None: Удаленный объект сессии, если найден, иначе None.
        """
        session_to_remove = self.sessions.get(session_id) # Получаем сессию перед удалением для Kafka сообщения
        if session_to_remove:
            # Отправляем сообщение в Kafka об удалении сессии
            kafka_message = {
                "event_type": "session_removed",
                "session_id": session_id,
                "timestamp": time.time(),
                "reason": reason # Добавляем причину удаления
            }
            send_kafka_message(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, kafka_message)
            
            # Теперь удаляем сессию из словаря активных сессий
            session = self.sessions.pop(session_id, None) 
            if session: # Должно быть всегда True, если session_to_remove был найден
                # Освобождаем всех игроков из этой сессии (удаляем из player_to_session)
                player_ids_in_session = list(session.players.keys()) # Копируем ключи, так как словарь будет изменяться
                for player_id in player_ids_in_session:
                    self.player_to_session.pop(player_id, None)
                logger.info(f"Session {session_id} removed by session manager. Reason: {reason}")
            return session # Возвращаем удаленную сессию
        logger.warning(f"Attempt to remove non-existent session: {session_id}")
        return None # Сессия не найдена

    def add_player_to_session(self, session_id, player_id, player_address, tank):
        """
        Добавляет игрока в указанную сессию.

        Проверяет, существует ли сессия и не находится ли игрок уже в другой сессии.
        Отправляет событие 'player_joined_session' в Kafka.

        Args:
            session_id (str): ID сессии, в которую добавляется игрок.
            player_id (any): ID игрока.
            player_address (any): Сетевой адрес игрока.
            tank (Tank): Объект танка, назначенный игроку.

        Returns:
            GameSession | None: Объект сессии, если игрок успешно добавлен, иначе None.
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Error: Session {session_id} not found when adding player {player_id}.")
            return None
        if player_id in self.player_to_session:
            # Игрок уже в какой-то сессии, возможно, в этой же или другой.
            # Это может быть ошибкой логики или попыткой двойного входа.
            logger.error(f"Error: Player {player_id} is already in session {self.player_to_session[player_id]}.")
            return None
        
        if session.add_player(player_id, player_address, tank):
            self.player_to_session[player_id] = session_id # Обновляем маппинг игрок -> сессия
            # Отправляем сообщение в Kafka о присоединении игрока
            kafka_message = {
                "event_type": "player_joined_session",
                "session_id": session_id,
                "player_id": player_id,
                "tank_id": tank.tank_id, 
                "timestamp": time.time()
            }
            send_kafka_message(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, kafka_message)
            logger.info(f"Player {player_id} added to session {session_id}.")
            return session
        logger.warning(f"Failed to add player {player_id} to session {session_id} (possibly already in session).")
        return None

    def remove_player_from_session(self, player_id):
        """
        Удаляет игрока из его текущей сессии.

        Если после удаления игрока сессия становится пустой, она также удаляется.
        Отправляет событие 'player_left_session' в Kafka.

        Args:
            player_id (any): ID игрока для удаления.

        Returns:
            bool: True, если игрок успешно удален, False, если игрок не найден в активной сессии.
        """
        session_id = self.player_to_session.get(player_id) # Сначала получаем ID сессии
        if session_id:
            session = self.get_session(session_id)
            if session:
                player_data = session.players.get(player_id) # Получаем данные игрока для Kafka сообщения
                tank_id_for_message = player_data.get('tank_id') if player_data else None

                session.remove_player(player_id) # Игрок удаляется из session.players здесь
                self.player_to_session.pop(player_id, None) # Теперь удаляем из маппинга менеджера

                # Отправляем сообщение в Kafka о выходе игрока
                kafka_message = {
                    "event_type": "player_left_session",
                    "session_id": session_id,
                    "player_id": player_id,
                    "timestamp": time.time()
                }
                if tank_id_for_message: # Добавляем ID танка, если он был найден
                    kafka_message["tank_id"] = tank_id_for_message
                send_kafka_message(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, kafka_message)
                logger.info(f"Player {player_id} removed from session {session_id}.")
                
                # Если сессия стала пустой после удаления игрока, удаляем и сессию
                if session.get_players_count() == 0:
                    logger.info(f"Session {session_id} is empty after player {player_id} left, removing session.")
                    self.remove_session(session_id, reason="empty_session") # Передаем причину
                return True
        logger.warning(f"Player {player_id} not found in any active session during removal attempt.")
        return False

    def get_session_by_player_id(self, player_id):
        """
        Возвращает сессию, в которой находится игрок.

        Args:
            player_id (any): ID игрока.

        Returns:
            GameSession | None: Объект сессии, если игрок найден, иначе None.
        """
        session_id = self.player_to_session.get(player_id)
        if session_id:
            return self.get_session(session_id)
        return None

# Пример использования (для тестирования, если модуль запускается напрямую)
if __name__ == '__main__':
    # Настройка логирования для примера
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    from .tank_pool import TankPool # Предполагается, что tank_pool.py находится в том же каталоге
    from .tank import Tank # Для создания мок-танков или реальных, если не слишком сложно

    sm1 = SessionManager() # Первый экземпляр (или единственный, если Singleton работает)
    sm2 = SessionManager() # Должен быть тот же экземпляр, что и sm1
    logger.info(f"SM1 is SM2: {sm1 is sm2}") # Проверка Singleton

    tank_pool = TankPool(pool_size=2) # Создаем пул танков для теста

    # Создаем сессию
    session1 = sm1.create_session()
    logger.info(f"Created session ID: {session1.session_id}")
    
    # Определяем данные игроков и пытаемся получить для них танки
    player1_id = "player_A"
    player1_addr = ("127.0.0.1", 12345) # Пример адреса
    tank1 = tank_pool.acquire_tank() # Получаем танк из пула

    player2_id = "player_B"
    player2_addr = ("127.0.0.1", 54321)
    tank2 = tank_pool.acquire_tank()
    
    # Добавляем игроков в сессию
    if tank1:
        logger.info(f"Tank for player_A: ID {tank1.tank_id}")
        sm1.add_player_to_session(session1.session_id, player1_id, player1_addr, tank1)
    else:
        logger.warning("Failed to get tank for player_A")

    if tank2:
        logger.info(f"Tank for player_B: ID {tank2.tank_id}")
        sm1.add_player_to_session(session1.session_id, player2_id, player2_addr, tank2)
    else:
        # Если pool_size=1, это ожидаемое поведение для второго игрока
        logger.warning("Failed to get tank for player_B") 

    if session1: # Проверяем, что сессия была создана
        logger.info(f"Players in session {session1.session_id}: {session1.players}")
        logger.info(f"Tanks in session {session1.session_id}: {session1.tanks}")
    
    # Проверяем поиск сессии по ID игрока
    retrieved_session = sm1.get_session_by_player_id(player1_id)
    if retrieved_session:
        logger.info(f"Player {player1_id} is in session {retrieved_session.session_id}")

    # Удаляем первого игрока
    sm1.remove_player_from_session(player1_id)
    if tank1: # Возвращаем танк в пул, если он был получен
        tank_pool.release_tank(tank1.tank_id)
        logger.info(f"Tank {tank1.tank_id} returned to pool.")
    
    # Если последний игрок удален, сессия должна удалиться автоматически
    # (проверяем по логам или по состоянию sm1.sessions)
    sm1.remove_player_from_session(player2_id) 
    if tank2: # Возвращаем второй танк в пул
        tank_pool.release_tank(tank2.tank_id)
        logger.info(f"Tank {tank2.tank_id} returned to pool.")

    logger.info(f"Current sessions in SessionManager: {sm1.sessions}")
    logger.info(f"Tank pool state: available {len(tank_pool.available_tanks)}, in_use {len(tank_pool.in_use_tanks)}")
