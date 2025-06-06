import pytest
from unittest.mock import patch, call, ANY
import time

# Импортируем класс Tank и константы Kafka топиков
# Предполагается, что эти константы доступны в game_server.tank,
# например, если они импортированы туда из core.message_broker_clients
from game_server.tank import Tank, KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, KAFKA_DEFAULT_TOPIC_GAME_EVENTS


@pytest.fixture
def tank_fixture():
    # Используем другое имя для фикстуры, чтобы не конфликтовать с импортированным классом Tank
    return Tank(tank_id="test_tank_01", initial_position=(10, 20), health=150)

def test_tank_initialization(tank_fixture):
    assert tank_fixture.tank_id == "test_tank_01"
    assert tank_fixture.position == (10, 20)
    assert tank_fixture.health == 150
    assert tank_fixture.is_active is False
    assert tank_fixture.last_update_time == 0

def test_tank_initialization_defaults():
    default_tank = Tank(tank_id="default_tank")
    assert default_tank.tank_id == "default_tank"
    assert default_tank.position == (0, 0)
    assert default_tank.health == 100
    assert default_tank.is_active is False
    assert default_tank.last_update_time == 0

@patch('game_server.tank.send_kafka_message')
def test_tank_move(mock_send_kafka, tank_fixture):
    new_pos = (30, 40)

    with patch('time.time', return_value=11111.11111) as mock_time_call:
        tank_fixture.move(new_pos)

    expected_kafka_message = {
        "event_type": "tank_moved",
        "tank_id": tank_fixture.tank_id,
        "position": new_pos,
        "timestamp": 11111.11111
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, expected_kafka_message)
    assert tank_fixture.position == new_pos

    # Проверка второго вызова
    mock_send_kafka.reset_mock() # Сбрасываем мок для чистоты проверки второго вызова
    with patch('time.time', return_value=22222.22222) as mock_time_call_2:
        tank_fixture.move((50,60))

    expected_kafka_message_2 = {
        "event_type": "tank_moved",
        "tank_id": tank_fixture.tank_id,
        "position": (50,60),
        "timestamp": 22222.22222
    }
    # mock_send_kafka должен быть вызван один раз с момента reset_mock()
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, expected_kafka_message_2)
    assert tank_fixture.position == (50,60)


@patch('game_server.tank.send_kafka_message')
@patch('time.time', return_value=12345.0)
def test_tank_shoot(mock_time, mock_send_kafka, tank_fixture):
    current_pos = tank_fixture.position
    tank_fixture.shoot()

    expected_kafka_message = {
        "event_type": "tank_shot",
        "tank_id": tank_fixture.tank_id,
        "position_at_shot": current_pos,
        "timestamp": 12345.0
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_kafka_message)

@patch('game_server.tank.send_kafka_message')
@patch('time.time', return_value=10000.0)
def test_take_damage_no_destruction(mock_time, mock_send_kafka, tank_fixture):
    damage_taken = 50
    health_before = tank_fixture.health
    tank_fixture.take_damage(damage_taken)

    assert tank_fixture.health == health_before - damage_taken

    expected_damage_message = {
        "event_type": "tank_took_damage",
        "tank_id": tank_fixture.tank_id,
        "damage_taken": damage_taken,
        "current_health": tank_fixture.health, # health is now 100
        "health_before_damage": health_before, # health was 150
        "timestamp": 10000.0
    }
    mock_send_kafka.assert_called_once_with(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_damage_message)

@patch('game_server.tank.send_kafka_message')
@patch('time.time', return_value=20000.0)
def test_take_damage_with_destruction(mock_time, mock_send_kafka, tank_fixture):
    damage_taken = 150 # Точно равно здоровью
    health_before = tank_fixture.health # tank_fixture.health = 150

    # Ожидаем два разных значения времени для двух Kafka сообщений
    # Первое сообщение (урон) использует mock_time (20000.0)
    # Второе сообщение (уничтожение) также использует mock_time (20000.0)
    # так как time.time() мокируется на весь тест. Если бы time.time() вызывался дважды
    # и мы хотели разные значения, нужно было бы использовать side_effect=[20000.0, 20000.1]

    tank_fixture.take_damage(damage_taken)

    assert tank_fixture.health == 0

    expected_damage_message = {
        "event_type": "tank_took_damage",
        "tank_id": tank_fixture.tank_id,
        "damage_taken": damage_taken,
        "current_health": 0, # После урона, но до явного self.health = 0, current_health в сообщении будет max(0, health-damage)
        "health_before_damage": health_before,
        "timestamp": 20000.0
    }
    expected_destroyed_message = {
        "event_type": "tank_destroyed",
        "tank_id": tank_fixture.tank_id,
        "timestamp": 20000.0 # Использует то же мокированное время
    }

    assert mock_send_kafka.call_count == 2
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_damage_message)
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_destroyed_message)

@patch('game_server.tank.send_kafka_message')
@patch('time.time', return_value=30000.0)
def test_take_damage_more_than_health(mock_time, mock_send_kafka, tank_fixture):
    damage_taken = 200 # Больше чем здоровье (150)
    health_before = tank_fixture.health
    tank_fixture.take_damage(damage_taken)

    assert tank_fixture.health == 0

    expected_damage_message = {
        "event_type": "tank_took_damage",
        "tank_id": tank_fixture.tank_id,
        "damage_taken": damage_taken,
        "current_health": 0, # max(0, 150-200) is 0
        "health_before_damage": health_before,
        "timestamp": 30000.0
    }
    expected_destroyed_message = {
        "event_type": "tank_destroyed",
        "tank_id": tank_fixture.tank_id,
        "timestamp": 30000.0
    }
    assert mock_send_kafka.call_count == 2
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_damage_message)
    mock_send_kafka.assert_any_call(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, expected_destroyed_message)

def test_tank_reset(tank_fixture):
    tank_fixture.is_active = True
    tank_fixture.last_update_time = 123.456
    tank_fixture.position = (1,1)
    tank_fixture.health = 10

    tank_fixture.reset(initial_position=(5,5), health=50)

    assert tank_fixture.position == (5,5)
    assert tank_fixture.health == 50
    assert tank_fixture.is_active is False
    assert tank_fixture.last_update_time == 0

def test_tank_reset_defaults(tank_fixture):
    tank_fixture.is_active = True
    tank_fixture.last_update_time = 123.456
    tank_fixture.position = (1,1)
    tank_fixture.health = 10

    tank_fixture.reset()

    assert tank_fixture.position == (0,0)
    assert tank_fixture.health == 100
    assert tank_fixture.is_active is False
    assert tank_fixture.last_update_time == 0

def test_tank_get_state(tank_fixture):
    expected_state = {
        'id': tank_fixture.tank_id,
        'position': tank_fixture.position,
        'health': tank_fixture.health
    }
    assert tank_fixture.get_state() == expected_state

    # Изменяем состояние и проверяем снова
    with patch('game_server.tank.send_kafka_message'): # Мокируем, чтобы не влияло на тест get_state
        # Также мокируем time.time для консистентности, если take_damage его использует и не мокирован глобально
        with patch('time.time', return_value=40000.0):
             tank_fixture.move((1,2)) # move не использует time.time в своей логике, только для Kafka
             tank_fixture.take_damage(10) # health станет 140

    expected_state_updated = {
        'id': tank_fixture.tank_id,
        'position': (1,2), # Обновлено после move
        'health': 140      # Обновлено после take_damage
    }
    assert tank_fixture.get_state() == expected_state_updated
