# tests/unit/test_tcp_handler_game.py
# This file contains unit tests for the game server's TCP handler
# (game_server.tcp_handler.handle_game_client).
# Focus is on verifying correct command publishing to RabbitMQ and JSON responses.

import logging
# Basic logging setup for tests. Helps in tracing test execution.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')

import asyncio
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock # Mocking tools
import json # For working with JSON messages

# Import the function to be tested
from game_server.tcp_handler import handle_game_client 
# Player and GameRoom are typically complex and tested separately,
# or their behavior is fully mocked in these tests.
# Focus here is on interaction with RabbitMQ (via mock_publish_rabbitmq)
# and correct client responses.

class MockPlayer:
    """
    Simplified mock class for Player.
    Used to simulate a player object in TCP handler tests.
    Contains essential attributes and an async send_message method.
    """
    def __init__(self, writer, name="test_player", token="test_token"):
        self.writer = writer # StreamWriter object for sending messages to the player
        self.name = name # Player's name
        self.token = token # Player's session token
        self.address = ("127.0.0.1", 12345) # Example client address

    async def send_message(self, message: str):
        """
        Asynchronously sends a message to the player.
        Simulates the behavior of the real Player.send_message.
        """
        if self.writer and not self.writer.is_closing(): # If writer exists and is not closing
            self.writer.write(message.encode('utf-8') + b"\n") # Send message with a newline
            await self.writer.drain() # Wait for buffer to flush

# Using AsyncMock for publish_rabbitmq_message as it's an async function.
# new_callable=AsyncMock ensures the mock is asynchronous.
@patch('game_server.tcp_handler.publish_rabbitmq_message', new_callable=AsyncMock)
class TestGameTCPHandlerResponses(unittest.IsolatedAsyncioTestCase): # Renamed class for clarity
    """
    Test suite for verifying TCP handler's interaction with RabbitMQ and client JSON responses.
    Checks that commands received from the client are correctly published to RabbitMQ
    and that appropriate JSON confirmations/errors are sent back.
    """

    async def test_handle_game_client_shoot_command_publishes_and_confirms(self, mock_publish_rabbitmq: AsyncMock): # Renamed for clarity
        """
        Test: SHOOT command received from client is published to RabbitMQ,
        and a JSON confirmation is sent back to the client.
        Simulates a successful login sequence, then a SHOOT command.
        Verifies `publish_rabbitmq_message` is called and the correct JSON response is written.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader) 
        mock_writer = AsyncMock(spec=asyncio.StreamWriter) 
        mock_writer.is_closing.return_value = False 
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345) 
        
        login_command = "LOGIN test_user test_pass\n"
        shoot_command = "SHOOT\n"
        mock_reader.readuntil.side_effect = [ 
            login_command.encode('utf-8'),  
            shoot_command.encode('utf-8'),  
            ConnectionResetError()          # Simulate connection reset to exit handle_game_client loop
        ]

        mock_game_room = MagicMock() 
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() 

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance) as mock_player_class_constructor:
            await handle_game_client(mock_reader, mock_writer, mock_game_room) 

        expected_message_shoot = {
            "player_id": "test_user",
            "command": "shoot",
            "details": {"source": "tcp_handler"} 
        }
        await asyncio.sleep(0) 
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_shoot) 
        
        await asyncio.sleep(0) 
        expected_json_dict = {"status": "received", "command": "SHOOT"}
        expected_json_bytes = json.dumps(expected_json_dict).encode('utf-8')
        
        self.assertTrue(
            any(expected_json_bytes in call_args[0][0] for call_args in mock_writer.write.call_args_list if call_args[0]),
            f"JSON confirmation for SHOOT command ({expected_json_dict}) not found in writer calls: {mock_writer.write.call_args_list}"
        )

    async def test_handle_game_client_move_command_publishes_and_confirms(self, mock_publish_rabbitmq: AsyncMock): # Renamed for clarity
        """
        Test: MOVE command received from client is published to RabbitMQ,
        and a JSON confirmation is sent back.
        Simulates a successful login, then a MOVE command with coordinates.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        move_command = "MOVE 10 20\n" 
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            move_command.encode('utf-8'),
            ConnectionResetError() 
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        expected_message_move = {
            "player_id": "test_user",
            "command": "move",
            "details": {"new_position": [10, 20]} 
        }
        await asyncio.sleep(0) 
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_move) 
        
        await asyncio.sleep(0) 
        expected_json_dict = {"status": "received", "command": "MOVE"}
        expected_json_bytes = json.dumps(expected_json_dict).encode('utf-8')

        self.assertTrue(
            any(expected_json_bytes in call_args[0][0] for call_args in mock_writer.write.call_args_list if call_args[0]),
            f"JSON confirmation for MOVE command ({expected_json_dict}) not found in writer calls: {mock_writer.write.call_args_list}"
        )

    async def test_handle_game_client_unknown_command_sends_json_error(self, mock_publish_rabbitmq: AsyncMock): # Renamed for clarity
        """
        Test: An unknown command from the client is NOT published to RabbitMQ,
        and a JSON error message is sent to the client.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        unknown_command = "JUMP\n" 
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            unknown_command.encode('utf-8'),
            ConnectionResetError()
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() 
        
        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) 
        mock_publish_rabbitmq.assert_not_called() 
        
        await asyncio.sleep(0) 
        expected_json_dict = {"status": "error", "message": "UNKNOWN_COMMAND"}
        expected_json_bytes = json.dumps(expected_json_dict).encode('utf-8')

        self.assertTrue(
            any(expected_json_bytes in call_args[0][0] for call_args in mock_writer.write.call_args_list if call_args[0]),
            f"JSON response for UNKNOWN_COMMAND ({expected_json_dict}) not found in writer calls: {mock_writer.write.call_args_list}"
        )

if __name__ == '__main__':
    # Run tests if the file is executed directly
    unittest.main()