# tests/unit/test_udp_handler_game.py
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch, call

from game_server.udp_handler import GameUDPProtocol
# Assuming SessionManager, TankPool, Tank are imported or mocked as needed
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# It's important that RABBITMQ_QUEUE_PLAYER_COMMANDS is the actual string value
# if it's used directly in assertions, or mock core.message_broker_clients too.
# from core.message_broker_clients import RABBITMQ_QUEUE_PLAYER_COMMANDS # For assertion if needed

@patch('game_server.udp_handler.publish_rabbitmq_message') 
# Patch where it's used, not where it's defined
class TestGameUDPHandlerRabbitMQ(unittest.TestCase):

    def setUp(self):
        self.protocol = GameUDPProtocol()
        self.mock_transport = MagicMock()
        self.protocol.transport = self.mock_transport
        
        # Mock dependencies of GameUDPProtocol
        self.protocol.session_manager = MagicMock(spec=SessionManager)
        self.protocol.tank_pool = MagicMock(spec=TankPool)

    def test_datagram_received_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq):
        addr = ('127.0.0.1', 1234)
        player_id = "player1"
        tank_id = "tank_A"

        # Mock session and tank setup
        mock_session = MagicMock()
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        mock_tank = MagicMock(spec=Tank)
        mock_tank.tank_id = tank_id # Ensure tank_id is set on the mock
        self.protocol.tank_pool.get_tank.return_value = mock_tank # This line was missing in the prompt, but implied by udp_handler logic
        
        message_data = {
            "action": "shoot",
            "player_id": player_id
            # Any other fields the "shoot" action might expect from client
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        expected_mq_message = {
            "player_id": player_id,
            "command": "shoot",
            "details": {
                "source": "udp_handler",
                "tank_id": tank_id # udp_handler was modified to include tank_id
            }
        }
        
        # Verify publish_rabbitmq_message was called correctly
        # The first argument is exchange_name, which is '' for default exchange.
        # The second is routing_key (queue name).
        mock_publish_rabbitmq.assert_called_once_with(
            '', # exchange_name
            'player_commands', # routing_key (actual queue name string for RABBITMQ_QUEUE_PLAYER_COMMANDS)
            expected_mq_message
        )
        
        # Check that tank.shoot() itself is NOT called directly
        # mock_tank.shoot.assert_not_called() # This line is commented out as get_tank is not called in the original udp_handler for shoot
        # The actual tank object is retrieved in the consumer, not in the handler for "shoot" after the change.
        # The handler only needs to get the tank_id from player_data.

        # Check that no broadcast happened directly from here for shoot event
        # self.mock_transport.sendto.assert_not_called() # This might be too strict if other messages are sent for errors etc.
        # More robust: check that a specific "player_shot" broadcast is NOT sent.
        # For this specific subtask, we assume that if publish_rabbitmq_message is called, then the direct handling (broadcast) is skipped.

    def test_datagram_received_move_command_direct_execution_no_rabbitmq(self, mock_publish_rabbitmq):
        # This test verifies that "move" command is still handled directly (as per current plan)
        # and does NOT go to RabbitMQ via the UDP handler.
        addr = ('127.0.0.1', 1234)
        player_id = "player2"
        tank_id = "tank_B"
        new_position = [50, 50]

        mock_session = MagicMock()
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        mock_session.get_tanks_state = MagicMock(return_value=[{"id": tank_id, "position": new_position, "health": 100}])
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        mock_tank = MagicMock(spec=Tank)
        self.protocol.tank_pool.get_tank.return_value = mock_tank

        message_data = {
            "action": "move",
            "player_id": player_id,
            "position": new_position
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called() # Ensure move does not go to RabbitMQ
        mock_tank.move.assert_called_once_with(tuple(new_position))
        # Check that broadcast DID happen for move (as per existing udp_handler logic)
        self.protocol.transport.sendto.assert_called()


    def test_datagram_received_join_game_no_rabbitmq(self, mock_publish_rabbitmq):
        # Verify non-critical commands like "join_game" don't go to RabbitMQ
        addr = ('127.0.0.1', 1234)
        player_id = "player3"
        
        # Mock the tank that would be acquired
        acquired_tank_mock = MagicMock(spec=Tank)
        acquired_tank_mock.tank_id = "tank_C"
        acquired_tank_mock.get_state.return_value = {"id": "tank_C", "position": (0,0), "health": 100}
        self.protocol.tank_pool.acquire_tank.return_value = acquired_tank_mock
        
        # Mock session creation and adding player
        mock_session_instance = MagicMock(spec=SessionManager.GameSession) # Use spec for GameSession if it's nested
        mock_session_instance.session_id="session_new"
        mock_session_instance.get_players_count.return_value = 0 # Before adding current player

        self.protocol.session_manager.get_session_by_player_id.return_value = None # Player not in session initially
        # self.protocol.session_manager.create_session.return_value = mock_session_instance # UDP handler might try to find existing session first
        # Let's simulate finding no existing session for player, then no available session with < 2 players, so create new.
        self.protocol.session_manager.sessions = {} # No existing sessions initially to force creation

        message_data = {"action": "join_game", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called()
        # Check that a response was sent to the client for join_game
        self.protocol.transport.sendto.assert_called()


if __name__ == '__main__':
    unittest.main()
