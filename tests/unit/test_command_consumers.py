# tests/unit/test_command_consumers.py
import unittest
from unittest.mock import MagicMock, patch, call
import json

# Assuming the project structure allows this import path
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Используем порядок декораторов:
# 1. @patch('pika.BlockingConnection') 
# 2. @patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True)
# Class-level decorators removed
class TestPlayerCommandConsumer(unittest.TestCase):

    def setUp(self): 
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        
        self.consumer = PlayerCommandConsumer(
            session_manager=self.mock_session_manager,
            tank_pool=self.mock_tank_pool
        )
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_shoot_command_success(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
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

    def test_callback_unknown_command(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
                players={"player1": {"tank_id": "tank123"}}
            )
            self.mock_tank_pool.get_tank.return_value = MagicMock(spec=Tank)
            message_body = json.dumps({"player_id": "player1", "command": "fly", "details": {}})
            mock_method = MagicMock(delivery_tag=125)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=125)

    def test_callback_missing_player_id(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            message_body = json.dumps({"command": "shoot", "details": {}})
            mock_method = MagicMock(delivery_tag=126)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=126)

    def test_callback_player_not_in_session(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            self.mock_session_manager.get_session_by_player_id.return_value = None
            message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
            mock_method = MagicMock(delivery_tag=127)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=127)

    def test_callback_tank_not_found(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
                players={"player1": {"tank_id": "tank123"}}
            )
            self.mock_tank_pool.get_tank.return_value = None
            message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
            mock_method = MagicMock(delivery_tag=128)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=128)

    def test_callback_json_decode_error(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            message_body = "not a json string"
            mock_method = MagicMock(delivery_tag=129)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=129)

# Используем порядок декораторов:
# 1. @patch('pika.BlockingConnection') 
# 2. @patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True)
# Class-level decorators removed
class TestMatchmakingEventConsumer(unittest.TestCase):

    def setUp(self):
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_new_match_created(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
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
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            message_body = json.dumps({"event_type": "match_update", "details": {}})
            mock_method = MagicMock(delivery_tag=202)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_session_manager.create_session.assert_not_called()
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=202)

    def test_callback_json_decode_error_matchmaking(self):
        with patch('pika.BlockingConnection') as mock_pika_connection, \
             patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True) as mock_connect_and_declare:
            message_body = "definitely not json"
            mock_method = MagicMock(delivery_tag=203)
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=203)

if __name__ == '__main__':
    unittest.main()