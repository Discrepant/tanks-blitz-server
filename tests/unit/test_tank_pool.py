# tests/unit/test_tank_pool.py
# Этот файл содержит модульные тесты для TankPool (пула объектов танков)
# из модуля game_server.tank_pool, используя pytest и фикстуры.
import pytest # Импортируем pytest для написания и запуска тестов
from game_server.tank_pool import TankPool # Тестируемый класс
from game_server.tank import Tank # Класс Tank, необходимый для работы TankPool

@pytest.fixture(scope="function") # Фикстура будет создаваться для каждой тестовой функции
def tank_pool_instance():
    """
    Фикстура pytest для предоставления "чистого" экземпляра TankPool для каждого теста.
    Сбрасывает состояние Singleton TankPool перед созданием нового экземпляра
    с фиксированным размером пула для предсказуемости тестов.
    """
    # Сбрасываем _instance TankPool перед каждым тестом для обеспечения изоляции.
    # Это важно, так как TankPool реализован как Singleton, и тесты не должны
    # влиять друг на друга через состояние, оставшееся от предыдущего теста.
    TankPool._instance = None # "Сброс" Singleton-экземпляра
    pool = TankPool(pool_size=5) # Создаем новый пул с размером 5 для тестов
    return pool

def test_tank_pool_singleton(tank_pool_instance):
    """
    Тест для проверки, что TankPool является Singleton.
    Два последовательных вызова TankPool() должны возвращать один и тот же объект,
    если первый экземпляр уже был создан (что делает фикстура).
    """
    pool1 = tank_pool_instance # Получаем экземпляр через фикстуру
    pool2 = TankPool() # Повторный вызов конструктора (должен вернуть тот же экземпляр)
    assert pool1 is pool2, "TankPool должен быть Singleton (возвращать тот же экземпляр)."

def test_acquire_release_tank(tank_pool_instance):
    """
    Тест получения танка из пула (acquire_tank) и его возврата (release_tank).
    Проверяет, что танк помечается как активный при получении, добавляется в
    `in_use_tanks`, а при возврате помечается как неактивный, удаляется из
    `in_use_tanks` и его состояние сбрасывается.
    """
    pool = tank_pool_instance # Используем TankPool из фикстуры
    
    initial_in_use = len(pool.in_use_tanks) # Начальное количество используемых танков
    
    # Получаем танк
    tank1 = pool.acquire_tank()
    assert tank1 is not None, "Должен быть получен свободный танк."
    assert tank1.is_active is True, "Полученный танк должен быть помечен как активный."
    assert tank1.tank_id in pool.in_use_tanks, "ID полученного танка должен быть в словаре используемых."
    assert len(pool.in_use_tanks) == initial_in_use + 1, "Количество используемых танков должно увеличиться."

    tank1_id = tank1.tank_id # Сохраняем ID для возврата
    
    # Возвращаем танк в пул
    pool.release_tank(tank1_id)
    assert tank1.is_active is False, "Возвращенный танк должен быть помечен как неактивный (через tank.reset())."
    assert tank1_id not in pool.in_use_tanks, "ID возвращенного танка не должен быть в словаре используемых."
    assert len(pool.in_use_tanks) == initial_in_use, "Количество используемых танков должно вернуться к начальному."
    
    # Проверяем, что состояние танка было сброшено (например, здоровье)
    # Метод tank.reset() устанавливает здоровье в значение по умолчанию (100).
    assert tank1.health == 100, "Здоровье танка должно быть сброшено к значению по умолчанию."

def test_acquire_all_tanks_then_none(tank_pool_instance):
    """
    Тест получения всех доступных танков из пула.
    Проверяет, что после получения всех танков следующий вызов acquire_tank
    возвращает None. Также проверяет, что после возврата одного танка
    его можно снова получить.
    """
    pool = tank_pool_instance # Размер пула = 5, согласно фикстуре
    acquired_tanks = []
    
    # Получаем все 5 танков
    for _ in range(5):
        tank = pool.acquire_tank()
        assert tank is not None, "Не удалось получить танк, хотя они должны быть доступны."
        acquired_tanks.append(tank)
    
    assert len(pool.in_use_tanks) == 5, "Все танки из пула должны быть помечены как используемые."
    
    # Пытаемся получить еще один танк (сверх лимита)
    extra_tank = pool.acquire_tank()
    assert extra_tank is None, "Не должно быть свободных танков после получения всех из пула."

    # Освобождаем один из полученных танков
    released_tank_info = acquired_tanks[0]
    pool.release_tank(released_tank_info.tank_id)
    assert len(pool.in_use_tanks) == 4, "Количество используемых танков должно уменьшиться после возврата одного."
    
    # Пытаемся снова получить танк
    new_tank = pool.acquire_tank()
    assert new_tank is not None, "Освобожденный танк должен быть снова доступен для получения."
    # Проверяем, что это тот же самый объект танка, который был освобожден и затем сброшен.
    assert new_tank is released_tank_info, "Должен быть возвращен тот же экземпляр танка, который был освобожден."


def test_get_tank_by_id(tank_pool_instance):
    """
    Тест получения используемого танка по его ID.
    Проверяет, что `get_tank` возвращает корректный объект танка, если он активен,
    и None в противном случае или если ID не существует.
    """
    pool = tank_pool_instance
    tank1 = pool.acquire_tank() # Получаем танк
    assert tank1 is not None, "Не удалось получить танк для теста."
    
    # Пытаемся получить этот танк по его ID
    retrieved_tank = pool.get_tank(tank1.tank_id)
    assert retrieved_tank is tank1, "Должен быть возвращен тот же объект танка по его ID."
    
    # Пытаемся получить танк с несуществующим ID
    non_existent_tank = pool.get_tank("non_existent_id")
    assert non_existent_tank is None, "Попытка получить танк с несуществующим ID должна вернуть None."

    # Возвращаем танк в пул
    pool.release_tank(tank1.tank_id)
    # Пытаемся получить танк снова после его возврата (он больше не должен быть "in_use")
    retrieved_after_release = pool.get_tank(tank1.tank_id)
    assert retrieved_after_release is None, "Танк не должен быть доступен через get_tank после его возврата в пул (т.к. он не 'in_use')."
