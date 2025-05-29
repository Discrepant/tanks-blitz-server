# tests/unit/test_udp_handler_game.py
# This file contains unit tests for the game server's UDP handler
# (game_server.udp_handler.GameUDPProtocol).
# Tests focus on verifying correct processing of various UDP messages,
# including publishing commands to RabbitMQ and direct execution of some actions.

import asyncio
import json # For working with JSON messages
import unittest
from unittest.mock import MagicMock, patch, call # Mocking tools

# Import the class to be tested: GameUDPProtocol
from game_server.udp_handler import GameUDPProtocol
# Assume SessionManager, TankPool, Tank are imported or mocked as needed.
from game_server.session_manager import SessionManager, GameSession
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# It's important that RABBITMQ_QUEUE_PLAYER_COMMANDS is an up-to-date string value
# if used directly in assertions, or also mock core.message_broker_clients.
# from core.message_broker_clients import RABBITMQ_QUEUE_PLAYER_COMMANDS # For assertion, if necessary

# Mock the publish_rabbitmq_message function where it's used (in game_server.udp_handler).
# This allows us to check if it's called, and with what arguments,
# without actually sending messages to RabbitMQ.
@patch('game_server.udp_handler.publish_rabbitmq_message') 
class TestGameUDPHandler(unittest.TestCase): # Renamed class for clarity
    """
    Test suite for GameUDPProtocol.
    Focuses on UDP message handling, including interactions with RabbitMQ for 'shoot' and 'move' commands,
    and direct processing for 'join_game'.
    """

    def setUp(self):
        """
        Set up before each test.
        Creates an instance of GameUDPProtocol and mocks its transport and dependencies
        (SessionManager, TankPool).
        """
        self.protocol = GameUDPProtocol() # Create an instance of the protocol to be tested
        self.mock_transport = MagicMock(spec=asyncio.DatagramTransport) # Mock for UDP transport
        self.protocol.transport = self.mock_transport # Assign mock transport to the protocol
        
        # Mock dependencies of GameUDPProtocol
        self.protocol.session_manager = MagicMock(spec=SessionManager)
        self.protocol.tank_pool = MagicMock(spec=TankPool)

    def test_datagram_received_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Test: 'shoot' command received via UDP is correctly published to RabbitMQ.
        Simulates receiving a datagram with a 'shoot' command and checks
        that `publish_rabbitmq_message` is called with expected parameters.
        """
        addr = ('127.0.0.1', 1234) # Example client address
        player_id = "player1_shoot"
        tank_id = "tank_A_shoot"

        # Setup mocks for session
        mock_session = MagicMock(spec=GameSession)
        mock_session.session_id = "session_shoot_test" # Ensure session_id is present
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        # Form 'shoot' command message
        message_data = {"action": "shoot", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        expected_mq_message = {
            "player_id": player_id,
            "command": "shoot", 
            "details": {"source": "udp_handler", "tank_id": tank_id}
        }
        
        mock_publish_rabbitmq.assert_called_once_with(
            '', 
            'player_commands', 
            expected_mq_message
        )
        
    def test_datagram_received_move_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Test: 'move' command received via UDP is correctly published to RabbitMQ.
        Simulates receiving a datagram with a 'move' command and checks
        that `publish_rabbitmq_message` is called with expected parameters.
        """
        addr = ('127.0.0.1', 12345)
        player_id = "player2_move"
        tank_id = "tank_B_move"
        new_position = [50, 50] 

        mock_session = MagicMock(spec=GameSession)
        mock_session.session_id = "session_move_test" # Ensure session_id is present
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        message_data = {
            "action": "move",
            "player_id": player_id,
            "position": new_position
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        expected_mq_message = {
            "player_id": player_id,
            "command": "move",
            "details": {
                "source": "udp_handler",
                "tank_id": tank_id,
                "new_position": new_position
            }
        }
        mock_publish_rabbitmq.assert_called_once_with(
            '', 
            'player_commands', 
            expected_mq_message
        )

    def test_datagram_received_join_game_direct_processing(self, mock_publish_rabbitmq: MagicMock):
        """
        Test: 'join_game' command is processed directly and NOT published to RabbitMQ.
        Checks that relevant SessionManager and TankPool methods are called, and a response is sent.
        """
        addr = ('127.0.0.1', 54321)
        player_id = "player3_join"
        
        acquired_tank_mock = MagicMock(spec=Tank)
        acquired_tank_mock.tank_id = "tank_C_join"
        acquired_tank_mock.get_state.return_value = {"id": "tank_C_join", "position": (0,0), "health": 100}
        self.protocol.tank_pool.acquire_tank.return_value = acquired_tank_mock
        
        mock_created_session = MagicMock(spec=GameSession) 
        mock_created_session.session_id = "session_join_test" # Ensure session_id is present
        mock_created_session.get_players_count.return_value = 0 # Simulate empty session before join

        self.protocol.session_manager.get_session_by_player_id.return_value = None 
        self.protocol.session_manager.create_session.return_value = mock_created_session 
        self.protocol.session_manager.sessions = {} # Simulate no active sessions initially

        message_data = {"action": "join_game", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called() 
        self.protocol.tank_pool.acquire_tank.assert_called_once()
        self.protocol.session_manager.add_player_to_session.assert_called_once_with(
            mock_created_session.session_id, player_id, addr, acquired_tank_mock
        )
        self.protocol.transport.sendto.assert_called_once() # Check that a response was sent
        # Check the content of the response if necessary
        args, _ = self.protocol.transport.sendto.call_args
        response_payload = json.loads(args[0].decode())
        self.assertEqual(response_payload["status"], "joined")
        self.assertEqual(response_payload["session_id"], "session_join_test")
        self.assertEqual(response_payload["tank_id"], "tank_C_join")


if __name__ == '__main__':
    # Run tests if the file is executed directly.
    unittest.main()
