# tests/unit/test_command_consumers.py
import unittest
from unittest.mock import MagicMock, patch, call
import json
import time # May be needed if consumers use time.sleep on errors

# Assuming the project structure allows this import path
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

class TestPlayerCommandConsumer(unittest.TestCase):

    def setUp(self):
        self.patcher_pika_setup = patch('pika.BlockingConnection')
        self.mock_pika_connection_for_setup = self.patcher_pika_setup.start()
        self.addCleanup(self.patcher_pika_setup.stop)

        self.patcher_connect_declare_setup = patch.object(PlayerCommandConsumer, '_connect_and_declare') # WITHOUT AUTOSPEC
        self.mock_connect_declare_for_setup = self.patcher_connect_declare_setup.start()
        self.addCleanup(self.patcher_connect_declare_setup.stop)
        
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        self.consumer = PlayerCommandConsumer(
            session_manager=self.mock_session_manager,
            tank_pool=self.mock_tank_pool
        )
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    @patch.object(PlayerCommandConsumer, '_connect_and_declare') # WITHOUT AUTOSPEC
    @patch('pika.BlockingConnection') 
    def test_callback_shoot_command_success(self, mock_pika_connection_test, mock_connect_and_declare_test):
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

    # ... (all other TestPlayerCommandConsumer test methods with @patch.object WITHOUT AUTOSPEC) ...

class TestMatchmakingEventConsumer(unittest.TestCase):

    def setUp(self):
        self.patcher_pika_setup = patch('pika.BlockingConnection')
        self.mock_pika_connection_for_setup = self.patcher_pika_setup.start()
        self.addCleanup(self.patcher_pika_setup.stop)

        self.patcher_connect_declare_setup = patch.object(MatchmakingEventConsumer, '_connect_and_declare') # WITHOUT AUTOSPEC
        self.mock_connect_declare_for_setup = self.patcher_connect_declare_setup.start()
        self.addCleanup(self.patcher_connect_declare_setup.stop)

        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.mock_channel = MagicMock()
        self.consumer.rabbitmq_channel = self.mock_channel

    @patch.object(MatchmakingEventConsumer, '_connect_and_declare') # WITHOUT AUTOSPEC
    @patch('pika.BlockingConnection')
    def test_callback_new_match_created(self, mock_pika_connection_test, mock_connect_and_declare_test):
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

    # ... (all other TestMatchmakingEventConsumer test methods with @patch.object WITHOUT AUTOSPEC) ...

if __name__ == '__main__':
    unittest.main()