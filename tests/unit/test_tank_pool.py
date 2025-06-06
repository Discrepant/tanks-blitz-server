import pytest
from unittest.mock import patch, MagicMock, call

# Импортируем класс TankPool и Tank (Tank нужен для мокирования и type hinting)
from game_server.tank_pool import TankPool
from game_server.tank import Tank


# Важно: TankPool - это Singleton. Тесты должны это учитывать.
# Чтобы сбрасывать состояние Singleton между тестами, если это необходимо,
# можно вручную устанавливать TankPool._instance = None в setup/teardown фикстуры.
@pytest.fixture(autouse=True)
def reset_tank_pool_singleton():
    # Эта фикстура будет автоматически применяться к каждому тесту
    # и сбрасывать состояние Singleton перед каждым тестом.
    TankPool._instance = None
    # Также сбросим 'initialized', если он был установлен на классе или предыдущем инстансе
    # Это важно для __init__ guard: if not hasattr(self, 'initialized')
    if hasattr(TankPool, 'initialized') and TankPool._instance is None :
         # Это условие не совсем верное, так как initialized - это атрибут экземпляра.
         # Если _instance None, то следующий созданный экземпляр не будет иметь initialized.
         # Правильнее будет, если TankPool() сам корректно обрабатывает повторную инициализацию
         # через hasattr(self, 'initialized'). Сброс _instance = None достаточен.
         pass


def test_tank_pool_singleton_instance(): # Тест экземпляра Singleton TankPool
    pool1 = TankPool(pool_size=5)
    pool2 = TankPool(pool_size=10) # Размер должен игнорироваться при втором вызове
    
    assert pool1 is pool2
    assert hasattr(pool1, 'pool'), "Экземпляр pool1 должен иметь атрибут 'pool' после инициализации" # Pool1 should have a 'pool' attribute after initialization
    assert len(pool1.pool) == 5 # Должен быть использован размер из первого вызова

@patch('game_server.tank_pool.Tank') # Мокируем класс Tank
def test_tank_pool_initialization(MockTank): # Тест инициализации TankPool
    # Настраиваем мок Tank для возврата мок-экземпляров с tank_id
    mock_instances = []
    def mock_tank_init(tank_id):
        instance = MagicMock(spec=Tank)
        instance.tank_id = tank_id
        instance.is_active = False # По умолчанию танки не активны
        instance.reset = MagicMock()
        mock_instances.append(instance)
        return instance
    MockTank.side_effect = mock_tank_init

    pool_size = 3
    # Сбрасываем _instance перед этим тестом, чтобы __init__ TankPool точно выполнился
    TankPool._instance = None
    if hasattr(TankPool, 'initialized'): # Для чистоты, если предыдущий тест не использовал фикстуру
        delattr(TankPool, 'initialized')


    pool = TankPool(pool_size=pool_size)

    assert len(pool.pool) == pool_size
    assert MockTank.call_count == pool_size
    # Проверяем, что Tank был вызван с правильными tank_id
    expected_calls = [call(tank_id=f"tank_{i}") for i in range(pool_size)]
    MockTank.assert_has_calls(expected_calls, any_order=False)
    
    assert isinstance(pool.in_use_tanks, dict)
    assert len(pool.in_use_tanks) == 0
    assert pool.initialized is True

    # Проверяем, что повторная инициализация не происходит
    MockTank.reset_mock()
    pool_again = TankPool(pool_size=100) # Этот pool_size должен быть проигнорирован
    assert pool_again is pool
    assert MockTank.call_count == 0 # Tank не должен был создаваться снова
    assert len(pool_again.pool) == pool_size # Размер остался от первой инициализации


@patch('game_server.tank_pool.TANKS_IN_USE')
@patch('game_server.tank_pool.Tank')
def test_acquire_tank_success(MockTank, mock_tanks_in_use): # Тест успешного получения танка
    # Сбрасываем _instance, чтобы TankPool был инициализирован с нашим MockTank
    TankPool._instance = None
    if hasattr(TankPool, 'initialized'):
        delattr(TankPool, 'initialized')

    # Настроим MockTank.side_effect, чтобы он возвращал заранее созданные моки
    # Это даст нам контроль над экземплярами в пуле.
    tank_in_pool = MagicMock(spec=Tank)
    tank_in_pool.tank_id = "tank_special_0"
    tank_in_pool.is_active = False # Свободен
    
    MockTank.side_effect = [tank_in_pool] # При инициализации пула будет создан этот танк

    pool = TankPool(pool_size=1) # Создаем пул с одним танком
    # pool.pool[0] теперь должен быть tank_in_pool
    
    # Убедимся, что in_use_tanks пуст перед тестом acquire
    pool.in_use_tanks = {}

    acquired_tank = pool.acquire_tank()

    assert acquired_tank is tank_in_pool
    assert acquired_tank.is_active is True
    assert "tank_special_0" in pool.in_use_tanks
    assert pool.in_use_tanks["tank_special_0"] is acquired_tank
    mock_tanks_in_use.inc.assert_called_once()

@patch('game_server.tank_pool.TANKS_IN_USE')
@patch('game_server.tank_pool.Tank')
def test_acquire_tank_none_available(MockTank, mock_tanks_in_use): # Тест получения танка, когда нет свободных
    TankPool._instance = None
    if hasattr(TankPool, 'initialized'):
        delattr(TankPool, 'initialized')

    tank_in_pool = MagicMock(spec=Tank)
    tank_in_pool.tank_id = "tank_busy_0"
    tank_in_pool.is_active = True # Танк занят
    MockTank.side_effect = [tank_in_pool]

    pool = TankPool(pool_size=1)
    # pool.pool[0] теперь tank_in_pool и он is_active = True
    # Дополнительно убедимся, что он в in_use_tanks, хотя acquire_tank не смотрит туда напрямую
    # pool.in_use_tanks = {tank_in_pool.tank_id: tank_in_pool} # Это не нужно, т.к. is_active уже True

    acquired_tank = pool.acquire_tank()
    assert acquired_tank is None
    mock_tanks_in_use.inc.assert_not_called()


@patch('game_server.tank_pool.TANKS_IN_USE')
@patch('game_server.tank_pool.Tank')
def test_release_tank_success(MockTank, mock_tanks_in_use): # Тест успешного освобождения танка
    TankPool._instance = None
    if hasattr(TankPool, 'initialized'):
        delattr(TankPool, 'initialized')

    tank_to_release = MagicMock(spec=Tank)
    tank_to_release.tank_id = "tank_to_release_0"
    tank_to_release.is_active = True
    tank_to_release.reset = MagicMock()
    
    # Вместо мокирования __init__ через MockTank.side_effect,
    # мы можем создать пул, а затем вручную установить его состояние.
    # Это проще для этого теста.
    pool = TankPool(pool_size=0) # Создаем пустой пул
    pool.pool = [tank_to_release]
    pool.in_use_tanks = {tank_to_release.tank_id: tank_to_release}

    pool.release_tank(tank_to_release.tank_id)

    assert tank_to_release.tank_id not in pool.in_use_tanks
    tank_to_release.reset.assert_called_once()
    mock_tanks_in_use.dec.assert_called_once()


@patch('game_server.tank_pool.TANKS_IN_USE')
def test_release_tank_not_in_use(mock_tanks_in_use): # Тест освобождения танка, который не используется
    # Этот тест не мокирует Tank, так что TankPool создаст реальные Tank объекты
    pool = TankPool(pool_size=1)
    
    initial_in_use_count = len(pool.in_use_tanks)
    with patch('game_server.tank_pool.logger') as mock_logger:
        pool.release_tank("non_existent_tank_id")
        mock_logger.warning.assert_called_once_with(
            "Warning: Attempt to release tank with ID (non_existent_tank_id) that is not in use or does not exist."
        )
    assert len(pool.in_use_tanks) == initial_in_use_count
    mock_tanks_in_use.dec.assert_not_called()


@patch('game_server.tank_pool.Tank')
def test_get_tank_success(MockTank): # Тест успешного получения используемого танка
    TankPool._instance = None # Сброс для чистоты
    if hasattr(TankPool, 'initialized'):
        delattr(TankPool, 'initialized')

    pool = TankPool(pool_size=0) # Инициализация пустого пула

    tank_in_use = MagicMock(spec=Tank)
    tank_in_use.tank_id = "tank_get_0"
    
    pool.in_use_tanks = {tank_in_use.tank_id: tank_in_use}

    retrieved_tank = pool.get_tank(tank_in_use.tank_id)
    assert retrieved_tank is tank_in_use

def test_get_tank_not_found(): # Тест получения несуществующего танка (autouse fixture сработает)
    pool = TankPool(pool_size=1) # Создаст реальные танки
    retrieved_tank = pool.get_tank("not_found_id")
    assert retrieved_tank is None

@patch('game_server.tank_pool.TANKS_IN_USE')
@patch('game_server.tank_pool.Tank')
def test_release_tank_calls_reset_which_sets_inactive(MockTank, mock_tanks_in_use): # Тест: release_tank вызывает reset, который устанавливает неактивность
    TankPool._instance = None
    if hasattr(TankPool, 'initialized'):
        delattr(TankPool, 'initialized')

    mock_tank_instance = MagicMock(spec=Tank)
    mock_tank_instance.tank_id = "tank_reset_test"
    mock_tank_instance.is_active = True

    # Моделируем поведение метода reset реального класса Tank
    def actual_reset_action():
        mock_tank_instance.is_active = False
        mock_tank_instance.position = (0,0)
        mock_tank_instance.health = 100
        mock_tank_instance.last_update_time = 0
    
    mock_tank_instance.reset = MagicMock(side_effect=actual_reset_action)
    
    pool = TankPool(pool_size=0) # пустой пул
    pool.pool = [mock_tank_instance] # добавляем наш мок в список всех танков
    pool.in_use_tanks = {mock_tank_instance.tank_id: mock_tank_instance} # он "в использовании"

    pool.release_tank(mock_tank_instance.tank_id)
    
    mock_tank_instance.reset.assert_called_once()
    mock_tanks_in_use.dec.assert_called_once() # Должен быть вызван dec
    assert mock_tank_instance.is_active is False # Проверяем, что is_active изменился

    # Проверяем, что танк теперь доступен для acquire
    # Сбрасываем мок для inc, так как он уже был вызван для dec
    mock_tanks_in_use.reset_mock()
    acquired_again = pool.acquire_tank()
    assert acquired_again is mock_tank_instance
    assert acquired_again.is_active is True # acquire_tank должен был установить is_active = True
    mock_tanks_in_use.inc.assert_called_once() # inc должен быть вызван при повторном получении
