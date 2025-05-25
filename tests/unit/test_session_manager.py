# tests/unit/test_session_manager.py
import pytest
from game_server.session_manager import SessionManager, GameSession
from game_server.tank_pool import TankPool
from game_server.tank import Tank

@pytest.fixture(scope="function")
def session_manager_instance():
    # Сброс синглтонов перед тестом
    SessionManager._instance = None
    TankPool._instance = None 
    sm = SessionManager()
    # Инициализируем TankPool, так как SessionManager может с ним взаимодействовать
    # (хотя в текущей реализации SessionManager напрямую не берет танки из пула,
    # это делает вызывающий код, но для полноты)
    _ = TankPool(pool_size=5) 
    return sm

@pytest.fixture
def tank_pool(): # Отдельная фикстура для пула танков
    TankPool._instance = None
    return TankPool(pool_size=5)

def test_session_manager_singleton(session_manager_instance):
    sm1 = session_manager_instance
    sm2 = SessionManager()
    assert sm1 is sm2

def test_create_get_remove_session(session_manager_instance):
    sm = session_manager_instance
    
    initial_session_count = len(sm.sessions)
    
    session = sm.create_session()
    assert session is not None
    assert isinstance(session, GameSession)
    assert session.session_id in sm.sessions
    assert len(sm.sessions) == initial_session_count + 1
    
    retrieved_session = sm.get_session(session.session_id)
    assert retrieved_session is session
    
    sm.remove_session(session.session_id)
    assert session.session_id not in sm.sessions
    assert len(sm.sessions) == initial_session_count
    assert sm.get_session(session.session_id) is None

def test_add_remove_player_from_session(session_manager_instance, tank_pool):
    sm = session_manager_instance
    session = sm.create_session()
    
    player1_id = "player1_test"
    player1_addr = ("1.2.3.4", 1111)
    tank1 = tank_pool.acquire_tank()
    assert tank1 is not None

    sm.add_player_to_session(session.session_id, player1_id, player1_addr, tank1)
    assert player1_id in session.players
    assert player1_id in sm.player_to_session
    assert sm.player_to_session[player1_id] == session.session_id
    assert session.players[player1_id]['tank_id'] == tank1.tank_id

    # Проверка получения сессии по ID игрока
    assert sm.get_session_by_player_id(player1_id) is session

    sm.remove_player_from_session(player1_id)
    # В session_manager.remove_player_from_session() есть логика удаления сессии если она пуста
    # session.players[player1_id] уже не будет существовать, если игрок удален из сессии
    # assert player1_id not in session.players # Это вызовет KeyError, если remove_player в сессии отработал
    assert sm.get_session_by_player_id(player1_id) is None # Игрок удален из player_to_session
    
    # Так как сессия стала пустой, она должна была удалиться
    assert session.session_id not in sm.sessions 
    # Важно: танк нужно вернуть в пул отдельно, SessionManager этим не занимается напрямую
    tank_pool.release_tank(tank1.tank_id)


def test_add_player_to_non_existent_session(session_manager_instance, tank_pool):
    sm = session_manager_instance
    player_id = "p_ghost"
    tank = tank_pool.acquire_tank()
    assert tank is not None # Убедимся, что танк получен
    result_session = sm.add_player_to_session("non_existent_session_id", player_id, ("1.1.1.1",123), tank)
    assert result_session is None
    assert player_id not in sm.player_to_session
    tank_pool.release_tank(tank.tank_id) # Не забываем вернуть танк

def test_remove_non_existent_player(session_manager_instance):
    sm = session_manager_instance
    session = sm.create_session() # Нужна хотя бы одна сессия для теста
    removed = sm.remove_player_from_session("non_existent_player")
    assert removed is False

def test_add_player_already_in_another_session(session_manager_instance, tank_pool):
    sm = session_manager_instance
    session1 = sm.create_session()
    session2 = sm.create_session() # Вторая сессия

    player_id = "player_multi_session"
    addr = ("1.2.3.5", 2222)
    tank_for_s1 = tank_pool.acquire_tank()
    tank_for_s2 = tank_pool.acquire_tank() # Отдельный танк для попытки добавления во вторую сессию

    assert tank_for_s1 is not None
    assert tank_for_s2 is not None

    # Добавляем игрока в первую сессию
    sm.add_player_to_session(session1.session_id, player_id, addr, tank_for_s1)
    assert sm.get_session_by_player_id(player_id) is session1

    # Пытаемся добавить того же игрока во вторую сессию
    result = sm.add_player_to_session(session2.session_id, player_id, addr, tank_for_s2)
    assert result is None # Не должен добавиться, т.к. уже в сессии
    assert session2.get_players_count() == 0 # Во второй сессии не должно быть игроков

    # Убедимся, что игрок все еще в первой сессии
    assert sm.get_session_by_player_id(player_id) is session1
    assert player_id in session1.players

    # Очистка
    tank_pool.release_tank(tank_for_s1.tank_id)
    tank_pool.release_tank(tank_for_s2.tank_id)
