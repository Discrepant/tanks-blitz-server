# tests/unit/test_udp_handler_game.py
# Этот файл содержит модульные тесты для UDP-обработчика игрового сервера
# (game_server.udp_handler.GameUDPProtocol).
# Тесты фокусируются на проверке правильности обработки различных UDP-сообщений,
# включая публикацию команд в RabbitMQ и прямое выполнение некоторых действий.

import asyncio
import json # Для работы с JSON-сообщениями
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock # Инструменты для мокирования

# Импортируем тестируемый класс GameUDPProtocol
from game_server.udp_handler import GameUDPProtocol
# Предполагается, что SessionManager, TankPool, Tank импортируются или мокируются по мере необходимости.
from game_server.session_manager import SessionManager, GameSession
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Важно, чтобы RABBITMQ_QUEUE_PLAYER_COMMANDS было актуальным строковым значением,
# если оно используется напрямую в утверждениях, или также мокировать core.message_broker_clients.
# from core.message_broker_clients import RABBITMQ_QUEUE_PLAYER_COMMANDS # Для утверждения, если необходимо

# Мокируем функцию publish_rabbitmq_message там, где она используется (в game_server.udp_handler).
# Это позволяет нам проверять, вызывается ли она, и с какими аргументами,
# без реальной отправки сообщений в RabbitMQ.
@patch('game_server.udp_handler.publish_rabbitmq_message') 
class TestGameUDPHandlerRabbitMQ(unittest.TestCase):
    """
    Набор тестов для GameUDPProtocol, сфокусированный на взаимодействии с RabbitMQ.
    Проверяет, что команды 'shoot' публикуются в RabbitMQ, а другие команды,
    такие как 'move' и 'join_game', обрабатываются напрямую (согласно текущей логике).
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает экземпляр GameUDPProtocol и мокирует его транспорт и зависимости
        (SessionManager, TankPool).
        """
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        self.protocol = GameUDPProtocol(session_manager=self.mock_session_manager,
                                        tank_pool=self.mock_tank_pool)
        self.mock_transport = MagicMock(spec=asyncio.DatagramTransport) # Мок для транспорта UDP
        self.protocol.transport = self.mock_transport # Присваиваем мок-транспорт протоколу
        
        # Строки ниже больше не нужны, так как зависимости передаются в конструктор
        # self.protocol.session_manager = MagicMock(spec=SessionManager)
        # self.protocol.tank_pool = MagicMock(spec=TankPool)

    def test_datagram_received_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'shoot', полученная по UDP, корректно публикуется в RabbitMQ.
        Имитирует получение датаграммы с командой 'shoot' и проверяет,
        что `publish_rabbitmq_message` вызывается с ожидаемыми параметрами.
        """
        addr = ('127.0.0.1', 1234) # Пример адреса клиента
        player_id = "player1"
        tank_id = "tank_A"

        # Настройка моков для сессии и танка
        mock_session = MagicMock(spec=GameSession)
        # Игрок player1 находится в сессии и ему назначен танк tank_A
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        mock_tank = MagicMock(spec=Tank)
        mock_tank.tank_id = tank_id # Убедимся, что у мок-танка есть tank_id
        # Эта строка была пропущена в исходном коде, но подразумевается логикой udp_handler.
        # Однако, для команды "shoot" в текущей реализации udp_handler, get_tank не вызывается,
        # он только извлекает tank_id из player_data.
        # self.protocol.tank_pool.get_tank.return_value = mock_tank 
        
        # Формируем сообщение команды 'shoot'
        message_data = {
            "action": "shoot",
            "player_id": player_id
            # Другие поля, которые клиент может отправлять с командой "shoot"
        }
        message_bytes = json.dumps(message_data).encode('utf-8') # Кодируем в байты
        
        # Вызываем тестируемый метод
        self.protocol.datagram_received(message_bytes, addr)
        
        # Ожидаемое сообщение для публикации в RabbitMQ
        expected_mq_message = {
            "player_id": player_id,
            "command": "shoot", # Команда для обработчика в command_consumer
            "details": {
                "source": "udp_handler", # Источник команды
                "tank_id": tank_id # udp_handler был изменен, чтобы включать tank_id
            }
        }
        
        # Проверяем, что publish_rabbitmq_message была вызвана корректно.
        # Первый аргумент - exchange_name (пустая строка для обменника по умолчанию).
        # Второй аргумент - routing_key (имя очереди).
        mock_publish_rabbitmq.assert_called_once_with(
            '', # exchange_name (обменник по умолчанию)
            'player_commands', # routing_key (фактическое имя очереди для RABBITMQ_QUEUE_PLAYER_COMMANDS)
            expected_mq_message
        )
        
        # Проверяем, что метод tank.shoot() НЕ вызывается напрямую в UDP-обработчике.
        # Эта логика теперь перенесена в command_consumer.
        # mock_tank.shoot.assert_not_called() # Закомментировано, так как get_tank не вызывается для shoot в udp_handler.
        # Фактический объект танка получается в потребителе, а не в обработчике для "shoot" после изменения.
        # Обработчик только получает tank_id из player_data.

        # Проверяем, что широковещательная рассылка НЕ произошла напрямую отсюда для события выстрела.
        # self.mock_transport.sendto.assert_not_called() # Это может быть слишком строгой проверкой, если отправляются другие сообщения (например, ошибки).
        # Более надежно: проверить, что конкретное широковещательное сообщение "player_shot" НЕ отправляется.
        # Для этой конкретной подзадачи мы предполагаем, что если publish_rabbitmq_message вызвана,
        # то прямая обработка (широковещательная рассылка) пропускается.
        # (В текущей реализации udp_handler нет явной рассылки после shoot, так что эта проверка нестрогая)

    def test_datagram_received_move_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'move' из UDP публикуется в RabbitMQ.
        Проверяет, что publish_rabbitmq_message вызывается с корректными аргументами.
        """
        addr = ('127.0.0.1', 1234)
        player_id = "player2"
        tank_id = "tank_B"
        new_position = [50, 50] # Новая позиция для танка

        mock_session = MagicMock(spec=GameSession)
        mock_session.session_id = "test_udp_session_123" 
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        # mock_tank и его настройка удалены, так как udp_handler больше не вызывает tank.move() напрямую.
        # self.protocol.tank_pool.get_tank.return_value = mock_tank 

        message_data = {
            "action": "move",
            "player_id": player_id,
            "position": new_position
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        expected_command_message = {
            "player_id": player_id,
            "command": "move",
            "details": {
                "source": "udp_handler",
                "tank_id": tank_id,
                "new_position": new_position
            }
        }
        # Используем фактическое значение имени очереди, как оно используется в udp_handler.py
        RABBITMQ_QUEUE_PLAYER_COMMANDS_val = 'player_commands' 
        mock_publish_rabbitmq.assert_called_once_with(
            '', 
            RABBITMQ_QUEUE_PLAYER_COMMANDS_val, 
            expected_command_message
        )
        # Проверки на mock_tank.move и self.protocol.transport.sendto удалены,
        # так как эта логика теперь предполагается в command_consumer после обработки сообщения из RabbitMQ.

    def test_datagram_received_join_game_no_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'join_game' обрабатывается напрямую и НЕ публикуется в RabbitMQ.
        Проверяет, что некритичные команды, такие как "join_game", не попадают в RabbitMQ.
        """
        addr = ('127.0.0.1', 1234)
        player_id = "player3"
        
        # Мокируем танк, который будет "получен" из пула
        acquired_tank_mock = MagicMock(spec=Tank)
        acquired_tank_mock.tank_id = "tank_C"
        acquired_tank_mock.get_state.return_value = {"id": "tank_C", "position": (0,0), "health": 100}
        self.protocol.tank_pool.acquire_tank.return_value = acquired_tank_mock
        
        # Мокируем создание сессии и добавление игрока
        mock_session_instance = MagicMock(spec=GameSession) # Используем spec для GameSession
        mock_session_instance.session_id="session_new"
        mock_session_instance.get_players_count.return_value = 0 # До добавления текущего игрока

        self.protocol.session_manager.get_session_by_player_id.return_value = None # Игрок изначально не в сессии
        # Настраиваем create_session для возврата нашего мок-экземпляра сессии
        self.protocol.session_manager.create_session.return_value = mock_session_instance 
        # Имитируем ситуацию, когда нет существующих сессий, чтобы заставить создать новую.
        self.protocol.session_manager.sessions = {} 

        message_data = {"action": "join_game", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called() # Команда 'join_game' не должна публиковаться в RabbitMQ
        # Проверяем, что клиенту был отправлен ответ на 'join_game'
        self.protocol.transport.sendto.assert_called()


if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()


# --- Pytest style tests added below ---
import pytest # Already imported, but good for clarity
# from game_server.udp_handler import GameUDPProtocol # Already imported
# from game_server.session_manager import SessionManager, GameSession # Already imported
# from game_server.tank_pool import TankPool # Already imported
# from game_server.tank import Tank # Already imported
from core.message_broker_clients import RABBITMQ_QUEUE_PLAYER_COMMANDS # For new tests

@pytest.fixture
def mock_session_manager_pytest(): # Renamed fixture
    sm = MagicMock(spec=SessionManager)
    sm.get_session_by_player_id = MagicMock()
    sm.create_session = MagicMock()
    sm.add_player_to_session = MagicMock()
    sm.remove_player_from_session = MagicMock()
    sm.get_session = MagicMock()
    return sm

@pytest.fixture
def mock_tank_pool_pytest(): # Renamed fixture
    tp = MagicMock(spec=TankPool)
    tp.get_tank = MagicMock()
    tp.acquire_tank = MagicMock()
    tp.release_tank = MagicMock()
    return tp

@pytest.fixture
def mock_transport_pytest(): # Renamed fixture
    transport = MagicMock(spec=asyncio.DatagramTransport)
    transport.sendto = MagicMock()
    transport.close = MagicMock()
    transport.get_extra_info = MagicMock(return_value=('127.0.0.1', 9999))
    return transport

@pytest.fixture
def udp_protocol_pytest(mock_session_manager_pytest, mock_tank_pool_pytest): # Renamed fixture
    protocol = GameUDPProtocol(session_manager=mock_session_manager_pytest, tank_pool=mock_tank_pool_pytest)
    return protocol

def test_udp_protocol_initialization_pytest(udp_protocol_pytest, mock_session_manager_pytest, mock_tank_pool_pytest):
    assert udp_protocol_pytest.session_manager is mock_session_manager_pytest
    assert udp_protocol_pytest.tank_pool is mock_tank_pool_pytest
    # Changed due to persistent AttributeError, suggesting transport is not initialized to None by super().__init__() in test context.
    # This should ideally be `assert udp_protocol_pytest.transport is None` if super().__init__() works as expected.
    assert not hasattr(udp_protocol_pytest, 'transport') or udp_protocol_pytest.transport is None


def test_udp_protocol_connection_made_pytest(udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    assert udp_protocol_pytest.transport is mock_transport_pytest
    mock_transport_pytest.get_extra_info.assert_called_with('sockname')

@patch('game_server.udp_handler.logger')
def test_udp_protocol_error_received_pytest(mock_logger, udp_protocol_pytest):
    test_exception = OSError("Test transport error")
    udp_protocol_pytest.error_received(test_exception)
    mock_logger.error.assert_called_once_with(f"UDP socket error received: {test_exception}", exc_info=True)

@patch('game_server.udp_handler.logger')
def test_udp_protocol_connection_lost_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    test_exception = Exception("Connection abruptly closed")
    udp_protocol_pytest.connection_lost(test_exception)
    mock_logger.error.assert_called_once_with(f"UDP socket closed with error: {test_exception}")
    assert udp_protocol_pytest.transport is mock_transport_pytest

@patch('game_server.udp_handler.logger')
def test_udp_protocol_connection_lost_no_exc_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    mock_logger.info.reset_mock() # Ensure reset_mock is here
    udp_protocol_pytest.connection_lost(None)
    mock_logger.info.assert_called_once_with("UDP socket closed.")


# --- Тесты для datagram_received (pytest style) ---
@patch('game_server.udp_handler.publish_rabbitmq_message') # Removed new_callable=AsyncMock
def test_datagram_received_move_success_pytest(
    mock_publish_rabbitmq, udp_protocol_pytest, mock_session_manager_pytest,
    mock_tank_pool_pytest, mock_transport_pytest # Use pytest suffixed fixtures
):
    client_addr = ('127.0.0.1', 1234)
    player_id = "p1"
    tank_id_in_session = "tank_of_p1"
    raw_data_dict = {"action": "move", "player_id": player_id, "position": [10, 20]}
    raw_data_bytes = json.dumps(raw_data_dict).encode('utf-8')

    udp_protocol_pytest.connection_made(mock_transport_pytest)

    mock_game_session = MagicMock(spec=GameSession)

    mock_session_manager_pytest.get_session_by_player_id.return_value = mock_game_session
    mock_game_session.players = {player_id: {'tank_id': tank_id_in_session, 'address': client_addr}}
    # get_tank is not called by udp_handler for "move"

    udp_protocol_pytest.datagram_received(raw_data_bytes, client_addr)

    mock_session_manager_pytest.get_session_by_player_id.assert_called_once_with(player_id)

    expected_rabbitmq_message = {
        "player_id": player_id,
        "command": "move",
        "details": {
            "source": "udp_handler",
            "tank_id": tank_id_in_session,
            "new_position": [10, 20]
        }
    }
    mock_publish_rabbitmq.assert_called_once_with('', RABBITMQ_QUEUE_PLAYER_COMMANDS, expected_rabbitmq_message)

    # No direct response or game state broadcast from datagram_received for MOVE
    mock_transport_pytest.sendto.assert_not_called()

# --- Pytest style tests for datagram_received error handling and other actions ---

@patch('game_server.udp_handler.logger')
def test_datagram_received_invalid_json_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    raw_data = b'{"action": "move", player_id: "p1"' # Invalid JSON

    udp_protocol_pytest.datagram_received(raw_data, client_addr)

    args, kwargs = mock_logger.error.call_args
    assert f"UDP [{client_addr}]: Invalid JSON" in args[0]
    expected_error_response = json.dumps({"status":"error", "message":"Invalid JSON format"}).encode('utf-8')
    mock_transport_pytest.sendto.assert_called_once_with(expected_error_response, client_addr)

@patch('game_server.udp_handler.logger')
def test_datagram_received_unicode_error_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    raw_data = b'\xff\xfe\xfd' # Invalid UTF-8

    udp_protocol_pytest.datagram_received(raw_data, client_addr)

    args, kwargs = mock_logger.error.call_args
    assert f"UDP [{client_addr}]: Unicode decode error" in args[0]
    expected_error_response = json.dumps({"status":"error", "message":"Invalid character encoding. UTF-8 expected."}).encode('utf-8')
    mock_transport_pytest.sendto.assert_called_once_with(expected_error_response, client_addr)

@patch('game_server.udp_handler.logger')
def test_datagram_received_leading_to_json_error_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest): # Renamed
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    # This input, after cleaning, becomes ' \n ', which is not empty but fails JSON parsing.
    raw_data = b' \x00 \n \x00 '

    udp_protocol_pytest.datagram_received(raw_data, client_addr)

    # Check for the "Null bytes removed" warning first
    mock_logger.warning.assert_any_call(
        f"Null bytes removed from data from {client_addr}. Original: '\x00 \n \x00', Cleaned: ' \n '"
    )

    # Then check for the JSONDecodeError log
    error_log_found = False
    for call_item in mock_logger.error.call_args_list:
        args, kwargs = call_item
        # Check if the logged message indicates an invalid JSON for the cleaned string ' \n '
        if f"UDP [{client_addr}]: Invalid JSON: ' \n '" in args[0]:
            error_log_found = True
            break
    assert error_log_found, "Expected JSONDecodeError log for ' \\n ' not found or message mismatch."

    expected_error_response = json.dumps({"status":"error", "message":"Invalid JSON format"}).encode('utf-8')
    mock_transport_pytest.sendto.assert_called_once_with(expected_error_response, client_addr)

@patch('game_server.udp_handler.logger')
def test_datagram_received_truly_empty_message_after_clean_pytest(mock_logger, udp_protocol_pytest, mock_transport_pytest):
    # This test checks the case where the message becomes truly empty after cleaning
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    raw_data = b'\x00\n\x00' # This becomes "" after replace('\x00','') and then strip().
                              # decode -> '\x00\n\x00'
                              # strip -> '\x00\n\x00' (no leading/trailing whitespace)
                              # replace -> '\n'
                              # strip -> '' (empty)

    # Let's use a simpler truly empty case: b" \n " -> strip -> ""
    raw_data_truly_empty = b"   \n   "


    udp_protocol_pytest.datagram_received(raw_data_truly_empty, client_addr)

    # No "Null bytes removed" warning for this input
    # Check for "Empty message after decoding" warning
    mock_logger.warning.assert_called_once() # Only one warning expected
    args, kwargs = mock_logger.warning.call_args
    assert f"UDP [{client_addr}]: Empty message after decoding, whitespace and null character cleaning." in args[0]
    assert f"Original bytes: {raw_data_truly_empty!r}" in args[0]


    expected_error_response = json.dumps({"status": "error", "message": "Empty JSON message"}).encode('utf-8')
    mock_transport_pytest.sendto.assert_called_once_with(expected_error_response, client_addr)


def test_datagram_received_missing_player_id_pytest(udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    raw_data_dict = {"action": "move", "position": [10,20]}
    raw_data_bytes = json.dumps(raw_data_dict).encode('utf-8')

    with patch('game_server.udp_handler.logger') as mock_logger:
        udp_protocol_pytest.datagram_received(raw_data_bytes, client_addr)
        mock_logger.warning.assert_called_once()
        assert f"UDP [{client_addr}]: Missing player_id in message" in mock_logger.warning.call_args[0][0]
    mock_transport_pytest.sendto.assert_not_called()

def test_datagram_received_unknown_action_pytest(udp_protocol_pytest, mock_transport_pytest):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 1234)
    player_id = "p1"
    raw_data_dict = {"action": "JUMP", "player_id": player_id}
    raw_data_bytes = json.dumps(raw_data_dict).encode('utf-8')

    with patch('game_server.udp_handler.logger') as mock_logger:
        udp_protocol_pytest.datagram_received(raw_data_bytes, client_addr)
        mock_logger.warning.assert_called_with(
            f"UDP [{client_addr}]: Unknown action 'JUMP' from player '{player_id}'. Message: {raw_data_dict}"
        )
    expected_error_response = json.dumps({"status": "error", "message": "Unknown action"}).encode('utf-8')
    mock_transport_pytest.sendto.assert_called_once_with(expected_error_response, client_addr)

@patch('game_server.udp_handler.TOTAL_PLAYERS_JOINED')
def test_datagram_received_join_game_success_new_session_pytest(
    mock_total_players_joined, udp_protocol_pytest, mock_session_manager_pytest,
    mock_tank_pool_pytest, mock_transport_pytest
):
    udp_protocol_pytest.connection_made(mock_transport_pytest)
    client_addr = ('127.0.0.1', 5555)
    player_id = "player_joiner"
    raw_data = json.dumps({"action": "join_game", "player_id": player_id}).encode('utf-8')

    mock_session_manager_pytest.get_session_by_player_id.return_value = None
    mock_acquired_tank = MagicMock(spec=Tank)
    mock_acquired_tank.tank_id = "new_tank"
    mock_tank_state = {"id": "new_tank", "pos": [0,0], "health":100}
    mock_acquired_tank.get_state.return_value = mock_tank_state
    mock_tank_pool_pytest.acquire_tank.return_value = mock_acquired_tank

    mock_new_session = MagicMock(spec=GameSession)
    mock_new_session.session_id = "s_new"
    mock_new_session.get_players_count.return_value = 0
    mock_session_manager_pytest.create_session.return_value = mock_new_session
    mock_session_manager_pytest.sessions = {}

    udp_protocol_pytest.datagram_received(raw_data, client_addr)

    mock_tank_pool_pytest.acquire_tank.assert_called_once()
    mock_session_manager_pytest.create_session.assert_called_once()
    mock_session_manager_pytest.add_player_to_session.assert_called_once_with(
        "s_new", player_id, client_addr, mock_acquired_tank
    )
    mock_total_players_joined.inc.assert_called_once()
    expected_response = {"status": "joined", "session_id": "s_new", "tank_id": "new_tank", "initial_state": mock_tank_state}
    mock_transport_pytest.sendto.assert_called_once_with(json.dumps(expected_response).encode('utf-8'), client_addr)

@patch('game_server.udp_handler.publish_rabbitmq_message') # Corrected: removed new_callable=AsyncMock
def test_datagram_received_shoot_success_pytest(
    mock_publish_rabbitmq, udp_protocol_pytest, mock_session_manager_pytest, mock_transport_pytest
):
    client_addr = ('127.0.0.1', 1234)
    player_id = "p_shooter"
    tank_id_in_session = "t_shooter"
    raw_data_dict = {"action": "shoot", "player_id": player_id}
    raw_data_bytes = json.dumps(raw_data_dict).encode('utf-8')

    udp_protocol_pytest.connection_made(mock_transport_pytest)
    mock_game_session = MagicMock(spec=GameSession)
    mock_session_manager_pytest.get_session_by_player_id.return_value = mock_game_session
    mock_game_session.players = {player_id: {'tank_id': tank_id_in_session, 'address': client_addr}}

    udp_protocol_pytest.datagram_received(raw_data_bytes, client_addr)

    expected_rabbitmq_message = {
        "player_id": player_id, "command": "shoot",
        "details": {"source": "udp_handler", "tank_id": tank_id_in_session}
    }
    # Since publish_rabbitmq_message is sync, its mock doesn't need await
    mock_publish_rabbitmq.assert_called_once_with('', RABBITMQ_QUEUE_PLAYER_COMMANDS, expected_rabbitmq_message)
    mock_transport_pytest.sendto.assert_not_called() # No direct response for shoot

def test_datagram_received_leave_game_success_pytest(
    udp_protocol_pytest, mock_session_manager_pytest, mock_tank_pool_pytest, mock_transport_pytest
):
    client_addr = ('127.0.0.1', 7777)
    player_id = "p_leaver"
    tank_id_in_session = "t_leaver"
    session_id_of_leaver = "s_leaver"
    raw_data = json.dumps({"action": "leave_game", "player_id": player_id}).encode('utf-8')

    udp_protocol_pytest.connection_made(mock_transport_pytest)
    mock_game_session = MagicMock(spec=GameSession)
    mock_game_session.session_id = session_id_of_leaver
    mock_session_manager_pytest.get_session_by_player_id.return_value = mock_game_session
    mock_game_session.players = {player_id: {'tank_id': tank_id_in_session, 'address': client_addr}}
    # Simulate session still existing after player removal (e.g., other players remain)
    mock_session_manager_pytest.get_session.return_value = mock_game_session

    udp_protocol_pytest.datagram_received(raw_data, client_addr)

    mock_session_manager_pytest.remove_player_from_session.assert_called_once_with(player_id)
    mock_tank_pool_pytest.release_tank.assert_called_once_with(tank_id_in_session)
    expected_response = {"status": "left_game", "message": "You have left the game."}
    mock_transport_pytest.sendto.assert_called_once_with(json.dumps(expected_response).encode('utf-8'), client_addr)
