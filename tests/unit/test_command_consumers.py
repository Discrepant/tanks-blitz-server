import unittest
from unittest.mock import MagicMock, patch, call
import json
import time # May be needed if consumers use time.sleep on errors

# Assuming the project structure allows this import path
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank # Needed for mock tank interactions

# Mock pika and other external dependencies if necessary at the module level for all tests
# For example, if consumers try to connect on __init__
# We can patch 'pika.BlockingConnection' to prevent actual network calls during tests.

@patch('pika.BlockingConnection')
@patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True)
class TestPlayerCommandConsumer(unittest.TestCase):

    def setUp(self, mock_pika_connection, mock_connect_and_declare):
        # Mock dependencies
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        
        # Instantiate the consumer with mock dependencies
        # The pika.BlockingConnection is already patched at class level
        self.consumer = PlayerCommandConsumer(
            session_manager=self.mock_session_manager,
            tank_pool=self.mock_tank_pool
        )
        # Mock the channel that would be created by pika
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel # Manually assign mock channel

    def test_callback_shoot_command_success(self, mock_pika_connection, mock_connect_and_declare):
        mock_tank_instance = MagicMock(spec=Tank)
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = mock_tank_instance
        
        message_body = json.dumps({
            "player_id": "player1",
            "command": "shoot",
            "details": {}
        })
        mock_method = MagicMock(delivery_tag=123)
        
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.get_session_by_player_id.assert_called_once_with("player1")
        self.mock_tank_pool.get_tank.assert_called_once_with("tank123")
        mock_tank_instance.shoot.assert_called_once()
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=123)

    def test_callback_move_command_success(self, mock_pika_connection, mock_connect_and_declare):
        mock_tank_instance = MagicMock(spec=Tank)
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = mock_tank_instance
        
        new_position = [10, 20]
        message_body = json.dumps({
            "player_id": "player1",
            "command": "move",
            "details": {"new_position": new_position}
        })
        mock_method = MagicMock(delivery_tag=124)
        
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        
        mock_tank_instance.move.assert_called_once_with(tuple(new_position))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=124)

    def test_callback_unknown_command(self, mock_pika_connection, mock_connect_and_declare):
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = MagicMock(spec=Tank)

        message_body = json.dumps({"player_id": "player1", "command": "fly", "details": {}})
        mock_method = MagicMock(delivery_tag=125)
        
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=125)
        # Ensure no tank methods like shoot or move were called

    def test_callback_missing_player_id(self, mock_pika_connection, mock_connect_and_declare):
        message_body = json.dumps({"command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=126)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=126)

    def test_callback_player_not_in_session(self, mock_pika_connection, mock_connect_and_declare):
        self.mock_session_manager.get_session_by_player_id.return_value = None
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=127)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=127)

    def test_callback_tank_not_found(self, mock_pika_connection, mock_connect_and_declare):
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = None
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=128)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=128)

    def test_callback_json_decode_error(self, mock_pika_connection, mock_connect_and_declare):
        message_body = "not a json string"
        mock_method = MagicMock(delivery_tag=129)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=129)

@patch('pika.BlockingConnection')
@patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True)
class TestMatchmakingEventConsumer(unittest.TestCase):

    def setUp(self, mock_pika_connection, mock_connect_and_declare):
        self.mock_session_manager = MagicMock(spec=SessionManager)
        # The pika.BlockingConnection is already patched at class level
        # The _connect_and_declare is patched by the method decorator and passed as mock_connect_and_declare
        self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_new_match_created(self, mock_pika_connection, mock_connect_and_declare):
        mock_created_session = MagicMock()
        mock_created_session.session_id = "new_session_1"
        self.mock_session_manager.create_session.return_value = mock_created_session
        
        message_body = json.dumps({
            "event_type": "new_match_created",
            "match_details": {"map_id": "map_desert", "max_players": 4}
        })
        mock_method = MagicMock(delivery_tag=201)
        
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.create_session.assert_called_once()
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=201)

    def test_callback_unknown_event_type(self, mock_pika_connection, mock_connect_and_declare):
        message_body = json.dumps({"event_type": "match_update", "details": {}})
        mock_method = MagicMock(delivery_tag=202)
        
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.create_session.assert_not_called()
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=202)

    def test_callback_json_decode_error_matchmaking(self, mock_pika_connection, mock_connect_and_declare):
        message_body = "definitely not json"
        mock_method = MagicMock(delivery_tag=203)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=203)

if __name__ == '__main__':
    unittest.main()
