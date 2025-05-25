# tests/unit/test_tank_pool.py
import pytest
from game_server.tank_pool import TankPool
from game_server.tank import Tank # Убедитесь, что Tank импортируется правильно

@pytest.fixture(scope="function") # Новый пул для каждого теста функции
def tank_pool_instance():
    # Сбрасываем синглтон перед каждым тестом, если это необходимо для изоляции
    # Однако, TankPool спроектирован так, что pool_size задается при первой инициализации.
    # Для тестов может быть лучше создавать экземпляр напрямую, минуя __new__ синглтона,
    # или добавить метод сброса в сам TankPool для тестовых нужд.
    # Пока что будем полагаться на то, что pool_size по умолчанию достаточно большой.
    TankPool._instance = None # "Сброс" синглтона для тестов
    pool = TankPool(pool_size=5)
    return pool

def test_tank_pool_singleton(tank_pool_instance):
    pool1 = tank_pool_instance
    pool2 = TankPool() # Должен вернуть тот же экземпляр, что и pool1
    assert pool1 is pool2

def test_acquire_release_tank(tank_pool_instance):
    pool = tank_pool_instance
    
    initial_in_use = len(pool.in_use_tanks)
    tank1 = pool.acquire_tank()
    assert tank1 is not None
    assert tank1.is_active is True
    assert tank1.tank_id in pool.in_use_tanks
    assert len(pool.in_use_tanks) == initial_in_use + 1

    tank1_id = tank1.tank_id
    pool.release_tank(tank1_id)
    assert tank1.is_active is False # reset должен это сделать
    assert tank1_id not in pool.in_use_tanks
    assert len(pool.in_use_tanks) == initial_in_use
    
    # Проверяем, что танк сброшен (например, здоровье)
    assert tank1.health == 100 # Значение по умолчанию из reset

def test_acquire_all_tanks_then_none(tank_pool_instance):
    pool = tank_pool_instance # pool_size=5
    acquired_tanks = []
    for _ in range(5):
        tank = pool.acquire_tank()
        assert tank is not None
        acquired_tanks.append(tank)
    
    assert len(pool.in_use_tanks) == 5
    
    extra_tank = pool.acquire_tank()
    assert extra_tank is None # Больше нет свободных танков

    # Освобождаем один
    pool.release_tank(acquired_tanks[0].tank_id)
    assert len(pool.in_use_tanks) == 4
    
    new_tank = pool.acquire_tank()
    assert new_tank is not None # Теперь один снова доступен
    # Проверяем, что это тот же объект танка, который был освобожден
    assert new_tank is acquired_tanks[0]


def test_get_tank_by_id(tank_pool_instance):
    pool = tank_pool_instance
    tank1 = pool.acquire_tank()
    assert tank1 is not None
    
    retrieved_tank = pool.get_tank(tank1.tank_id)
    assert retrieved_tank is tank1
    
    non_existent_tank = pool.get_tank("non_existent_id")
    assert non_existent_tank is None

    pool.release_tank(tank1.tank_id)
    retrieved_after_release = pool.get_tank(tank1.tank_id)
    assert retrieved_after_release is None # Танк больше не "in_use"
