# tests/unit/test_session_manager.py
# Этот файл содержит модульные тесты для SessionManager и GameSession
# из модуля game_server.session_manager, используя pytest и фикстуры.
import pytest # Импортируем pytest для написания и запуска тестов
from game_server.session_manager import SessionManager, GameSession # Тестируемые классы
from game_server.tank_pool import TankPool # Пул танков, используется для создания танков
from game_server.tank import Tank # Класс танка

@pytest.fixture(scope="function") # Фикстура будет создаваться для каждой тестовой функции
def session_manager_instance():
    """
    Фикстура pytest для предоставления "чистого" экземпляра SessionManager
    и связанного с ним TankPool для каждого теста.
    Сбрасывает состояние Singleton-ов SessionManager и TankPool перед созданием.
    """
    # Сброс состояния Singleton перед каждым тестом для изоляции.
    SessionManager._instance = None
    TankPool._instance = None 
    sm = SessionManager() # Создаем новый экземпляр SessionManager
    # Инициализируем TankPool, так как SessionManager (или код, использующий его)
    # может с ним взаимодействовать при добавлении игроков (выдаче танков).
    # Хотя в текущей реализации SessionManager напрямую не берет танки из пула
    # (это делает вызывающий код, например, UDP-обработчик), для полноты и
    # возможного будущего взаимодействия лучше инициализировать пул.
    _ = TankPool(pool_size=5) # Размер пула 5 для тестов
    return sm

@pytest.fixture
def tank_pool():
    """
    Фикстура pytest для предоставления "чистого" экземпляра TankPool.
    Сбрасывает состояние Singleton TankPool перед созданием.
    """
    TankPool._instance = None # Сброс Singleton TankPool
    return TankPool(pool_size=5) # Возвращаем новый экземпляр с размером пула 5

def test_session_manager_singleton(session_manager_instance):
    """
    Тест для проверки, что SessionManager является Singleton.
    Два последовательных вызова SessionManager() должны возвращать один и тот же объект.
    """
    sm1 = session_manager_instance # Получаем экземпляр через фикстуру (уже создал объект)
    sm2 = SessionManager() # Повторный вызов конструктора
    assert sm1 is sm2, "SessionManager должен быть Singleton (возвращать тот же экземпляр)."

def test_create_get_remove_session(session_manager_instance):
    """
    Тест создания, получения и удаления игровой сессии.
    Проверяет, что сессия корректно добавляется в словарь активных сессий,
    может быть получена по ID, и затем удаляется.
    """
    sm = session_manager_instance # Используем SessionManager из фикстуры
    
    initial_session_count = len(sm.sessions) # Начальное количество сессий
    
    session = sm.create_session() # Создаем новую сессию
    assert session is not None, "Созданная сессия не должна быть None."
    assert isinstance(session, GameSession), "Созданный объект должен быть экземпляром GameSession."
    assert session.session_id in sm.sessions, "ID новой сессии должен быть в словаре активных сессий."
    assert len(sm.sessions) == initial_session_count + 1, "Количество сессий должно увеличиться на 1."
    
    retrieved_session = sm.get_session(session.session_id) # Получаем сессию по ID
    assert retrieved_session is session, "Полученная сессия должна совпадать с созданной."
    
    sm.remove_session(session.session_id) # Удаляем сессию
    assert session.session_id not in sm.sessions, "ID удаленной сессии не должен быть в словаре активных сессий."
    assert len(sm.sessions) == initial_session_count, "Количество сессий должно вернуться к начальному."
    assert sm.get_session(session.session_id) is None, "Попытка получить удаленную сессию должна возвращать None."

def test_add_remove_player_from_session(session_manager_instance, tank_pool):
    """
    Тест добавления игрока в сессию и его последующего удаления.
    Проверяет, что игрок корректно регистрируется в сессии и в общем маппинге
    `player_to_session`. Также проверяет, что при удалении последнего игрока
    сессия автоматически удаляется.
    """
    sm = session_manager_instance
    session = sm.create_session() # Создаем сессию
    
    player1_id = "player1_test"
    player1_addr = ("1.2.3.4", 1111) # Пример адреса игрока
    tank1 = tank_pool.acquire_tank() # Получаем танк для игрока
    assert tank1 is not None, "Не удалось получить танк из пула."

    # Добавляем игрока в сессию
    sm.add_player_to_session(session.session_id, player1_id, player1_addr, tank1)
    assert player1_id in session.players, "Игрок должен быть в словаре игроков сессии."
    assert player1_id in sm.player_to_session, "Игрок должен быть в глобальном маппинге player_to_session."
    assert sm.player_to_session[player1_id] == session.session_id, "Маппинг player_to_session указывает на неверный ID сессии."
    assert session.players[player1_id]['tank_id'] == tank1.tank_id, "ID танка игрока в сессии указан неверно."

    # Проверка получения сессии по ID игрока
    assert sm.get_session_by_player_id(player1_id) is session, "Не удалось получить сессию по ID игрока."

    # Удаляем игрока из сессии
    sm.remove_player_from_session(player1_id)
    # В session_manager.remove_player_from_session() есть логика удаления сессии, если она пуста.
    # Поэтому session.players[player1_id] уже не будет существовать, если игрок был последним
    # и сессия удалилась. Проверяем через get_session_by_player_id.
    assert sm.get_session_by_player_id(player1_id) is None, "Игрок должен быть удален из player_to_session."
    
    # Так как это был единственный игрок, сессия должна была автоматически удалиться.
    assert session.session_id not in sm.sessions, "Сессия должна была удалиться, так как стала пустой."
    
    # Важно: танк нужно вернуть в пул отдельно. SessionManager этим не занимается напрямую.
    tank_pool.release_tank(tank1.tank_id)


def test_add_player_to_non_existent_session(session_manager_instance, tank_pool):
    """
    Тест попытки добавления игрока в несуществующую сессию.
    Проверяет, что игрок не добавляется и метод возвращает None.
    """
    sm = session_manager_instance
    player_id = "p_ghost" # "Призрачный" игрок
    tank = tank_pool.acquire_tank()
    assert tank is not None, "Не удалось получить танк для теста."
    
    # Пытаемся добавить игрока в сессию с несуществующим ID
    result_session = sm.add_player_to_session("non_existent_session_id", player_id, ("1.1.1.1", 123), tank)
    
    assert result_session is None, "Результат добавления в несуществующую сессию должен быть None."
    assert player_id not in sm.player_to_session, "Игрок не должен быть добавлен в player_to_session."
    tank_pool.release_tank(tank.tank_id) # Не забываем вернуть танк в пул

def test_remove_non_existent_player(session_manager_instance):
    """
    Тест попытки удаления несуществующего игрока из сессии.
    Проверяет, что метод `remove_player_from_session` возвращает False.
    """
    sm = session_manager_instance
    # Нужна хотя бы одна сессия для теста, чтобы было откуда удалять (хотя игрок и не будет найден)
    _ = sm.create_session() 
    
    removed = sm.remove_player_from_session("non_existent_player") # Пытаемся удалить несуществующего игрока
    assert removed is False, "Попытка удалить несуществующего игрока должна вернуть False."

def test_add_player_already_in_another_session(session_manager_instance, tank_pool):
    """
    Тест попытки добавления игрока, который уже находится в другой активной сессии.
    Проверяет, что игрок не добавляется во вторую сессию.
    """
    sm = session_manager_instance
    session1 = sm.create_session() # Первая сессия
    session2 = sm.create_session() # Вторая сессия

    player_id = "player_multi_session"
    addr = ("1.2.3.5", 2222)
    tank_for_s1 = tank_pool.acquire_tank()
    # Отдельный танк для попытки добавления во вторую сессию, чтобы избежать конфликтов с пулом
    tank_for_s2 = tank_pool.acquire_tank() 

    assert tank_for_s1 is not None, "Не удалось получить танк для первой сессии."
    assert tank_for_s2 is not None, "Не удалось получить танк для второй сессии."

    # Добавляем игрока в первую сессию
    sm.add_player_to_session(session1.session_id, player_id, addr, tank_for_s1)
    assert sm.get_session_by_player_id(player_id) is session1, "Игрок должен быть в первой сессии."

    # Пытаемся добавить того же игрока во вторую сессию
    result = sm.add_player_to_session(session2.session_id, player_id, addr, tank_for_s2)
    assert result is None, "Игрок не должен быть добавлен во вторую сессию, так как уже активен в другой."
    assert session2.get_players_count() == 0, "Во второй сессии не должно быть игроков."

    # Убедимся, что игрок все еще корректно числится в первой сессии
    assert sm.get_session_by_player_id(player_id) is session1, "Игрок должен оставаться в первой сессии."
    assert player_id in session1.players, "Игрок должен быть в списке игроков первой сессии."

    # Очистка: возвращаем танки в пул
    tank_pool.release_tank(tank_for_s1.tank_id)
    tank_pool.release_tank(tank_for_s2.tank_id)
