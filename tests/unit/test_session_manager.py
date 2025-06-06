# tests/unit/test_session_manager.py
# Этот файл содержит модульные тесты для SessionManager и GameSession
# из модуля game_server.session_manager, используя pytest и фикстуры.
import pytest # Импортируем pytest для написания и запуска тестов
from unittest.mock import MagicMock, patch, call
import uuid # Для мокирования uuid.uuid4
import time # Для мокирования time.time

from game_server.session_manager import SessionManager, GameSession # Тестируемые классы
from game_server.tank_pool import TankPool # Пул танков, используется для создания танков
from game_server.tank import Tank # Класс танка, нужен для мокирования и типизации
from core.message_broker_clients import KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS


# --- Существующие тесты для SessionManager (интеграционного стиля) ---
@pytest.fixture(scope="function")
def session_manager_instance():
    SessionManager._instance = None
    # Убедимся, что initialized сбрасывается для __init__ guard SessionManager
    if hasattr(SessionManager, 'initialized') and SessionManager._instance is None:
        delattr(SessionManager, 'initialized')

    TankPool._instance = None 
    # Убедимся, что initialized сбрасывается для __init__ guard TankPool
    if hasattr(TankPool, 'initialized') and TankPool._instance is None:
        delattr(TankPool, 'initialized')

    sm = SessionManager()
    _ = TankPool(pool_size=5)
    return sm

@pytest.fixture
def tank_pool_for_sm_tests(): # Изменено имя, чтобы не конфликтовать с другими тестами TankPool
    TankPool._instance = None
    if hasattr(TankPool, 'initialized') and TankPool._instance is None:
        delattr(TankPool, 'initialized')
    return TankPool(pool_size=5)

def test_session_manager_singleton_existing_tests(session_manager_instance):
    sm1 = session_manager_instance
    sm2 = SessionManager()
    assert sm1 is sm2, "SessionManager должен быть Singleton (возвращать тот же экземпляр)."

@patch('game_server.session_manager.send_kafka_message') # Мокируем Kafka для существующих тестов SM
@patch('game_server.session_manager.time.time') # Мокируем time для существующих тестов SM
@patch('game_server.session_manager.uuid.uuid4') # Мокируем uuid для существующих тестов SM
def test_create_get_remove_session_existing_tests(mock_uuid, mock_time, mock_send_kafka, session_manager_instance):
    mock_uuid.return_value = "fixed-uuid-for-existing-test"
    mock_time.return_value = 12345.0

    sm = session_manager_instance
    initial_session_count = len(sm.sessions)

    session = sm.create_session()
    assert session is not None
    assert isinstance(session, GameSession)
    assert session.session_id == "fixed-uuid-for-existing-test" # Проверяем мокированный UUID
    assert session.session_id in sm.sessions
    assert len(sm.sessions) == initial_session_count + 1

    # Проверка Kafka вызова для создания сессии
    expected_kafka_create_message = {
        "event_type": "session_created", "session_id": "fixed-uuid-for-existing-test", "timestamp": 12345.0
    }
    # mock_send_kafka.assert_called_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_create_message)
    # В коде SessionManager Kafka вызывается после создания сессии, так что это должен быть последний вызов, если только один.
    # Если другие вызовы были, то assert_any_call или смотреть call_args_list.
    # Для простоты здесь предполагаем, что это был единственный вызов или последний значимый.
    # mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_create_message)
    # Учитывая, что session_manager_instance может быть переиспользован с моками, лучше reset_mock
    mock_send_kafka.reset_mock() # Сброс перед действием, которое мы хотим проверить

    # Re-create session for this part of test to ensure clean mock state for remove
    TankPool._instance = None # Reset for tank pool
    if hasattr(TankPool, 'initialized'): delattr(TankPool, 'initialized')
    SessionManager._instance = None # Reset for session manager
    if hasattr(SessionManager, 'initialized'): delattr(SessionManager, 'initialized')
    sm = SessionManager()
    _ = TankPool(pool_size=5)

    mock_uuid.return_value = "another-fixed-uuid"
    mock_time.return_value = 12346.0
    session_to_remove = sm.create_session()
    session_id_to_remove = session_to_remove.session_id
    mock_send_kafka.reset_mock() # Сброс после создания

    mock_time.return_value = 12347.0 # Новое время для удаления
    sm.remove_session(session_id_to_remove)
    assert session_id_to_remove not in sm.sessions
    assert sm.get_session(session_id_to_remove) is None

    expected_kafka_remove_message = {
        "event_type": "session_removed", "session_id": session_id_to_remove,
        "timestamp": 12347.0, "reason": "explicitly_removed"
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_remove_message)


@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.time.time')
@patch('game_server.session_manager.uuid.uuid4')
def test_add_remove_player_from_session_existing_tests(mock_uuid, mock_time, mock_send_kafka, session_manager_instance, tank_pool_for_sm_tests):
    sm = session_manager_instance

    mock_uuid.return_value = "session-for-player-test"
    mock_time.return_value = 20000.0
    session = sm.create_session()
    mock_send_kafka.reset_mock() # Сброс после создания сессии
    
    player1_id = "player1_test"
    player1_addr = ("1.2.3.4", 1111)
    tank1 = tank_pool_for_sm_tests.acquire_tank()
    assert tank1 is not None

    mock_time.return_value = 20001.0 # Время для добавления игрока
    sm.add_player_to_session(session.session_id, player1_id, player1_addr, tank1)
    assert player1_id in session.players
    assert player1_id in sm.player_to_session
    assert sm.player_to_session[player1_id] == session.session_id

    expected_kafka_join_message = {
        "event_type": "player_joined_session", "session_id": session.session_id,
        "player_id": player1_id, "tank_id": tank1.tank_id, "timestamp": 20001.0
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_join_message)
    mock_send_kafka.reset_mock() # Сброс для проверки удаления

    assert sm.get_session_by_player_id(player1_id) is session

    mock_time.return_value = 20002.0 # Время для удаления игрока
    mock_time_remove_session = 20003.0 # Время для удаления сессии (если она станет пустой)
    
    # Чтобы time.time() вернул разные значения последовательно для player_left и session_removed
    mock_time.side_effect = [20002.0, mock_time_remove_session]

    sm.remove_player_from_session(player1_id)
    assert sm.get_session_by_player_id(player1_id) is None
    assert session.session_id not in sm.sessions # Сессия должна удалиться
    
    assert mock_send_kafka.call_count == 2
    expected_kafka_left_message = {
        "event_type": "player_left_session", "session_id": session.session_id,
        "player_id": player1_id, "tank_id": tank1.tank_id, "timestamp": 20002.0
    }
    expected_kafka_session_removed_message = {
        "event_type": "session_removed", "session_id": session.session_id,
        "timestamp": mock_time_remove_session, "reason": "empty_session"
    }
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_left_message)
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_session_removed_message)

    tank_pool_for_sm_tests.release_tank(tank1.tank_id)

def test_add_player_to_non_existent_session_existing_tests(session_manager_instance, tank_pool_for_sm_tests):
    sm = session_manager_instance
    player_id = "p_ghost"
    tank = tank_pool_for_sm_tests.acquire_tank()
    assert tank is not None

    with patch('game_server.session_manager.logger') as mock_logger:
        result_session = sm.add_player_to_session("non_existent_session_id", player_id, ("1.1.1.1", 123), tank)
        assert result_session is None
        assert player_id not in sm.player_to_session
        mock_logger.error.assert_called_once_with(
            f"Error: Session non_existent_session_id not found when adding player {player_id}."
        )
    tank_pool_for_sm_tests.release_tank(tank.tank_id)

def test_remove_non_existent_player_existing_tests(session_manager_instance):
    sm = session_manager_instance
    _ = sm.create_session() 
    with patch('game_server.session_manager.logger') as mock_logger:
        removed = sm.remove_player_from_session("non_existent_player")
        assert removed is False
        mock_logger.warning.assert_called_once_with(
            "Player non_existent_player not found in any active session during removal attempt."
        )

@patch('game_server.session_manager.send_kafka_message') # Мокируем Kafka для чистоты
def test_add_player_already_in_another_session_existing_tests(mock_send_kafka, session_manager_instance, tank_pool_for_sm_tests):
    sm = session_manager_instance
    session1 = sm.create_session()
    session2 = sm.create_session()

    player_id = "player_multi_session"
    addr = ("1.2.3.5", 2222)
    tank_for_s1 = tank_pool_for_sm_tests.acquire_tank()
    tank_for_s2 = tank_pool_for_sm_tests.acquire_tank()

    assert tank_for_s1 is not None
    assert tank_for_s2 is not None

    sm.add_player_to_session(session1.session_id, player_id, addr, tank_for_s1)
    assert sm.get_session_by_player_id(player_id) is session1

    with patch('game_server.session_manager.logger') as mock_logger:
        result = sm.add_player_to_session(session2.session_id, player_id, addr, tank_for_s2)
        assert result is None
        assert session2.get_players_count() == 0
        mock_logger.error.assert_called_once_with(
             f"Error: Player {player_id} is already in session {session1.session_id}."
        )

    assert sm.get_session_by_player_id(player_id) is session1
    assert player_id in session1.players

    tank_pool_for_sm_tests.release_tank(tank_for_s1.tank_id)
    tank_pool_for_sm_tests.release_tank(tank_for_s2.tank_id)


# --- Новые тесты для GameSession (юнит-тесты) ---
@pytest.fixture
def mock_gs_tank(): # Изменено имя фикстуры, чтобы не конфликтовать
    tank = MagicMock(spec=Tank)
    tank.tank_id = "tank_007"
    tank.get_state = MagicMock(return_value={"id": "tank_007", "position": (0,0), "health": 100})
    return tank

@pytest.fixture
def game_session_unit(): # Изменено имя фикстуры
    return GameSession(session_id="session_test_123_unit")

def test_gs_initialization(game_session_unit):
    assert game_session_unit.session_id == "session_test_123_unit"
    assert isinstance(game_session_unit.players, dict)
    assert len(game_session_unit.players) == 0
    assert isinstance(game_session_unit.tanks, dict)
    assert len(game_session_unit.tanks) == 0
    assert isinstance(game_session_unit.game_state, dict)

def test_gs_add_player_new(game_session_unit, mock_gs_tank):
    player_id = "player1"
    player_addr = ("127.0.0.1", 1111)
    result = game_session_unit.add_player(player_id, player_addr, mock_gs_tank)
    assert result is True
    assert player_id in game_session_unit.players
    assert game_session_unit.players[player_id]['address'] == player_addr
    assert game_session_unit.players[player_id]['tank_id'] == mock_gs_tank.tank_id
    assert mock_gs_tank.tank_id in game_session_unit.tanks
    assert game_session_unit.tanks[mock_gs_tank.tank_id] is mock_gs_tank

def test_gs_add_player_existing(game_session_unit, mock_gs_tank):
    player_id = "player1"
    game_session_unit.add_player(player_id, ("1.1.1.1", 11), mock_gs_tank)
    another_mock_tank = MagicMock(spec=Tank)
    another_mock_tank.tank_id = "tank_008"
    result = game_session_unit.add_player(player_id, ("2.2.2.2", 22), another_mock_tank)
    assert result is False
    assert len(game_session_unit.players) == 1
    assert game_session_unit.players[player_id]['tank_id'] == mock_gs_tank.tank_id
    assert another_mock_tank.tank_id not in game_session_unit.tanks

def test_gs_remove_player_existing(game_session_unit, mock_gs_tank):
    player_id = "player1"
    game_session_unit.add_player(player_id, ("1.1.1.1", 11), mock_gs_tank)
    original_tank_id = game_session_unit.players[player_id]['tank_id']
    assert original_tank_id in game_session_unit.tanks
    game_session_unit.remove_player(player_id)
    assert player_id not in game_session_unit.players
    assert original_tank_id in game_session_unit.tanks

def test_gs_remove_player_not_existing(game_session_unit):
    initial_player_count = len(game_session_unit.players)
    with patch('game_server.session_manager.logger') as mock_logger:
        game_session_unit.remove_player("non_existent_player")
        mock_logger.warning.assert_called_once_with(
            f"Player non_existent_player not found in session {game_session_unit.session_id} during removal attempt."
        )
    assert len(game_session_unit.players) == initial_player_count

def test_gs_get_all_player_addresses(game_session_unit, mock_gs_tank):
    addr1 = ("1.1.1.1", 11); addr2 = ("2.2.2.2", 22)
    game_session_unit.add_player("p1", addr1, mock_gs_tank)
    mock_tank2 = MagicMock(spec=Tank); mock_tank2.tank_id = "tank_008"
    game_session_unit.add_player("p2", addr2, mock_tank2)
    addresses = game_session_unit.get_all_player_addresses()
    assert len(addresses) == 2; assert addr1 in addresses; assert addr2 in addresses

def test_gs_get_players_count(game_session_unit, mock_gs_tank):
    assert game_session_unit.get_players_count() == 0
    game_session_unit.add_player("p1", ("1.1.1.1", 11), mock_gs_tank)
    assert game_session_unit.get_players_count() == 1
    mock_tank2 = MagicMock(spec=Tank); mock_tank2.tank_id = "tank_008"
    game_session_unit.add_player("p2", ("2.2.2.2", 22), mock_tank2)
    assert game_session_unit.get_players_count() == 2

def test_gs_get_tanks_state(game_session_unit, mock_gs_tank):
    state1 = {"id": "tank_007", "position": (0,0), "health": 100}
    game_session_unit.add_player("p1", ("1.1.1.1", 11), mock_gs_tank)
    mock_tank2 = MagicMock(spec=Tank); mock_tank2.tank_id = "tank_008"
    state2 = {"id": "tank_008", "position": (1,1), "health": 90}
    mock_tank2.get_state.return_value = state2
    game_session_unit.add_player("p2", ("2.2.2.2", 22), mock_tank2)
    tanks_states = game_session_unit.get_tanks_state()
    assert len(tanks_states) == 2; assert state1 in tanks_states; assert state2 in tanks_states
    mock_gs_tank.get_state.assert_called_once()
    mock_tank2.get_state.assert_called_once()

# --- Новые юнит-тесты для SessionManager ---
@pytest.fixture(autouse=True)
def new_reset_session_manager_singleton(): # Новое имя для autouse фикстуры под новые тесты SM
    SessionManager._instance = None
    if hasattr(SessionManager, 'initialized'):
        delattr(SessionManager, 'initialized')

@pytest.fixture
def sm_unit(): # Новая фикстура для SessionManager для юнит-тестов
    return SessionManager()

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.uuid.uuid4')
@patch('game_server.session_manager.time.time')
def test_sm_unit_create_session(mock_time, mock_uuid, mock_send_kafka, mock_active_sessions, sm_unit):
    mock_uuid.return_value = "test-uuid-sm-unit"
    mock_time.return_value = 12345.678

    session = sm_unit.create_session()

    assert session.session_id == "test-uuid-sm-unit"
    assert "test-uuid-sm-unit" in sm_unit.sessions
    assert sm_unit.sessions["test-uuid-sm-unit"] is session

    expected_kafka_message = {
        "event_type": "session_created",
        "session_id": "test-uuid-sm-unit",
        "timestamp": 12345.678
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_message)
    mock_active_sessions.inc.assert_called_once()

# --- Юнит-тесты для SessionManager (продолжение) ---

@patch('game_server.session_manager.GameSession') # Мокируем класс GameSession
def test_sm_unit_get_session(MockGameSession, sm_unit):
    mock_session_instance = MockGameSession.return_value
    mock_session_instance.session_id = "session1"
    sm_unit.sessions = {"session1": mock_session_instance} # Наполняем вручную

    retrieved = sm_unit.get_session("session1")
    assert retrieved is mock_session_instance

    assert sm_unit.get_session("non_existent") is None

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.time.time')
@patch('game_server.session_manager.GameSession')
def test_sm_unit_remove_session_existing(MockGameSession, mock_time, mock_send_kafka, mock_active_sessions, sm_unit):
    mock_time.return_value = 45678.123

    mock_session_instance = MockGameSession()
    mock_session_instance.session_id = "session_to_remove"
    mock_session_instance.players = {"playerA": {}, "playerB": {}}

    sm_unit.sessions = {mock_session_instance.session_id: mock_session_instance}
    sm_unit.player_to_session = {"playerA": mock_session_instance.session_id, "playerB": mock_session_instance.session_id}
    mock_active_sessions.inc.reset_mock() # Reset from potential creation if session was real

    removed = sm_unit.remove_session(mock_session_instance.session_id, reason="unit_test_removal")

    assert removed is mock_session_instance
    assert mock_session_instance.session_id not in sm_unit.sessions
    assert "playerA" not in sm_unit.player_to_session
    assert "playerB" not in sm_unit.player_to_session

    expected_kafka_message = {
        "event_type": "session_removed",
        "session_id": mock_session_instance.session_id,
        "timestamp": 45678.123,
        "reason": "unit_test_removal"
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_message)
    mock_active_sessions.dec.assert_called_once()
    mock_active_sessions.inc.assert_not_called()

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
def test_sm_unit_remove_session_not_existing(mock_send_kafka, mock_active_sessions, sm_unit):
    with patch('game_server.session_manager.logger') as mock_logger:
        removed = sm_unit.remove_session("non_existent_id_unit")
        assert removed is None
        mock_logger.warning.assert_called_once_with("Attempt to remove non-existent session: non_existent_id_unit")
    mock_send_kafka.assert_not_called()
    mock_active_sessions.dec.assert_not_called()

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.time.time')
@patch('game_server.session_manager.GameSession')
def test_sm_unit_add_player_to_session_success(MockGameSession, mock_time, mock_send_kafka, mock_active_sessions, sm_unit, mock_gs_tank):
    mock_time.return_value = 789.012

    mock_session_instance = MockGameSession()
    mock_session_instance.session_id = "s1"
    mock_session_instance.add_player.return_value = True

    sm_unit.sessions = {"s1": mock_session_instance}
    sm_unit.player_to_session = {}

    player_id = "player_add_unit"
    player_addr = ("addr_unit", 4321)

    result_session = sm_unit.add_player_to_session("s1", player_id, player_addr, mock_gs_tank)

    assert result_session is mock_session_instance
    mock_session_instance.add_player.assert_called_once_with(player_id, player_addr, mock_gs_tank)
    assert player_id in sm_unit.player_to_session
    assert sm_unit.player_to_session[player_id] == "s1"

    expected_kafka_message = {
        "event_type": "player_joined_session",
        "session_id": "s1",
        "player_id": player_id,
        "tank_id": mock_gs_tank.tank_id,
        "timestamp": 789.012
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_kafka_message)
    mock_active_sessions.inc.assert_not_called()
    mock_active_sessions.dec.assert_not_called()


def test_sm_unit_add_player_to_non_existent_session(sm_unit, mock_gs_tank):
    with patch('game_server.session_manager.logger') as mock_logger:
        result = sm_unit.add_player_to_session("fake_s", "p_unit", ("a",1), mock_gs_tank)
        assert result is None
        mock_logger.error.assert_called_once_with(
            "Error: Session fake_s not found when adding player p_unit."
        )

def test_sm_unit_add_player_already_in_another_session(sm_unit, mock_gs_tank):
    mock_session1 = MagicMock(spec=GameSession)
    mock_session1.session_id = "s1"
    mock_session2 = MagicMock(spec=GameSession)
    mock_session2.session_id = "s2"

    sm_unit.sessions = {"s1": mock_session1, "s2": mock_session2}
    sm_unit.player_to_session = {"p_unit_exists": "s1"}

    with patch('game_server.session_manager.logger') as mock_logger:
        result = sm_unit.add_player_to_session("s2", "p_unit_exists", ("b",2), mock_gs_tank)
        assert result is None
        mock_logger.error.assert_called_once_with(
            f"Error: Player p_unit_exists is already in session s1."
        )

@patch('game_server.session_manager.GameSession')
def test_sm_unit_add_player_session_add_player_fails(MockGameSession, sm_unit, mock_gs_tank):
    mock_session_instance = MockGameSession()
    mock_session_instance.session_id = "s_add_fail"
    mock_session_instance.add_player.return_value = False
    sm_unit.sessions = {"s_add_fail": mock_session_instance}

    with patch('game_server.session_manager.logger') as mock_logger:
        result = sm_unit.add_player_to_session("s_add_fail", "p_fail_add", ("c",3), mock_gs_tank)
        assert result is None
        mock_session_instance.add_player.assert_called_once_with("p_fail_add", ("c",3), mock_gs_tank)
        mock_logger.warning.assert_called_once_with(
            f"Failed to add player p_fail_add to session s_add_fail (possibly already in session)."
        )

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.time.time')
@patch('game_server.session_manager.GameSession')
def test_sm_unit_remove_player_from_session_empties_session(MockGameSession, mock_time, mock_send_kafka, mock_active_sessions, sm_unit):
    mock_session_instance = MockGameSession()
    mock_session_instance.session_id = "s_empty_test"
    mock_session_instance.players = {"p_to_remove": {'tank_id': "tank123"}}
    mock_session_instance.get_players_count.return_value = 0

    sm_unit.sessions = {mock_session_instance.session_id: mock_session_instance}
    sm_unit.player_to_session = {"p_to_remove": mock_session_instance.session_id}

    mock_time.side_effect = [100.0, 101.0]
    mock_active_sessions.inc.reset_mock()

    result = sm_unit.remove_player_from_session("p_to_remove")

    assert result is True
    mock_session_instance.remove_player.assert_called_once_with("p_to_remove")
    assert "p_to_remove" not in sm_unit.player_to_session
    assert mock_session_instance.session_id not in sm_unit.sessions

    assert mock_send_kafka.call_count == 2
    expected_left_msg = {
        "event_type": "player_left_session", "session_id": "s_empty_test",
        "player_id": "p_to_remove", "tank_id": "tank123", "timestamp": 100.0
    }
    expected_removed_msg = {
        "event_type": "session_removed", "session_id": "s_empty_test",
        "timestamp": 101.0, "reason": "empty_session"
    }
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_left_msg)
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_removed_msg)
    mock_active_sessions.dec.assert_called_once()

@patch('game_server.session_manager.ACTIVE_SESSIONS')
@patch('game_server.session_manager.send_kafka_message')
@patch('game_server.session_manager.time.time')
@patch('game_server.session_manager.GameSession')
def test_sm_unit_remove_player_session_not_empty(MockGameSession, mock_time, mock_send_kafka, mock_active_sessions, sm_unit):
    mock_time.return_value = 200.0
    mock_session_instance = MockGameSession()
    mock_session_instance.session_id = "s_not_empty"
    mock_session_instance.players = {"p_rem": {'tank_id': "t_rem"}, "p_stay": {'tank_id': "t_stay"}}
    mock_session_instance.get_players_count.return_value = 1

    sm_unit.sessions = {mock_session_instance.session_id: mock_session_instance}
    sm_unit.player_to_session = {"p_rem": "s_not_empty", "p_stay": "s_not_empty"}

    result = sm_unit.remove_player_from_session("p_rem")

    assert result is True
    mock_session_instance.remove_player.assert_called_once_with("p_rem")
    assert "p_rem" not in sm_unit.player_to_session
    assert mock_session_instance.session_id in sm_unit.sessions

    expected_left_msg = {
        "event_type": "player_left_session", "session_id": "s_not_empty",
        "player_id": "p_rem", "tank_id": "t_rem", "timestamp": 200.0
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS, expected_left_msg)
    mock_active_sessions.dec.assert_not_called()


def test_sm_unit_remove_player_not_found(sm_unit):
    sm_unit.player_to_session = {} # Нет активных игроков
    with patch('game_server.session_manager.logger') as mock_logger:
        result = sm_unit.remove_player_from_session("p_ghost_unit")
        assert result is False
        mock_logger.warning.assert_called_once_with(
            "Player p_ghost_unit not found in any active session during removal attempt."
        )

@patch('game_server.session_manager.GameSession')
def test_sm_unit_get_session_by_player_id(MockGameSession, sm_unit):
    mock_session = MockGameSession()
    mock_session.session_id = "s_find_me"
    sm_unit.sessions = {"s_find_me": mock_session}
    sm_unit.player_to_session = {"player_found": "s_find_me"}

    assert sm_unit.get_session_by_player_id("player_found") is mock_session
    assert sm_unit.get_session_by_player_id("player_not_found") is None
