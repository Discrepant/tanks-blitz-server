import unittest
from unittest.mock import MagicMock, patch, call
import json
import time # May be needed if consumers use time.sleep on errors

# Assuming the project structure allows this import path
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Class-level decorators are back, setUp will take mocks as arguments

@patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) # Outer decorator
@patch('pika.BlockingConnection') # Inner decorator
class TestPlayerCommandConsumer(unittest.TestCase):

    # setUp now takes mock arguments from class decorators
    # Order of args: self, mock_from_inner_decorator, mock_from_outer_decorator
    def setUp(self, mock_pika_connection, mock_connect_and_declare_consumer):
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        
        # mock_pika_connection and mock_connect_and_declare_consumer are now active
        # if PlayerCommandConsumer or its _connect_and_declare uses them during __init__
        self.consumer = PlayerCommandConsumer(
            session_manager=self.mock_session_manager,
            tank_pool=self.mock_tank_pool
        )
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel # For testing callbacks directly

    # Test methods no longer take individual mock arguments for these patches
    def test_callback_shoot_command_success(self):
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

    def test_callback_move_command_success(self):
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

    def test_callback_unknown_command(self):
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = MagicMock(spec=Tank)
        message_body = json.dumps({"player_id": "player1", "command": "fly", "details": {}})
        mock_method = MagicMock(delivery_tag=125)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=125)

    def test_callback_missing_player_id(self):
        message_body = json.dumps({"command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=126)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=126)

    def test_callback_player_not_in_session(self):
        self.mock_session_manager.get_session_by_player_id.return_value = None
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=127)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=127)

    def test_callback_tank_not_found(self):
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = None
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=128)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=128)

    def test_callback_json_decode_error(self):
        message_body = "not a json string"
        mock_method = MagicMock(delivery_tag=129)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=129)

@patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True) # Outer decorator
@patch('pika.BlockingConnection') # Inner decorator
class TestMatchmakingEventConsumer(unittest.TestCase):

    def setUp(self, mock_pika_connection, mock_connect_and_declare_consumer):
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_new_match_created(self):
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

    def test_callback_unknown_event_type(self):
        message_body = json.dumps({"event_type": "match_update", "details": {}})
        mock_method = MagicMock(delivery_tag=202)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_session_manager.create_session.assert_not_called()
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=202)

    def test_callback_json_decode_error_matchmaking(self):
        message_body = "definitely not json"
        mock_method = MagicMock(delivery_tag=203)
        self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
        self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=203)

if __name__ == '__main__':
    unittest.main()
