import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from game_server.udp_handler import GameUDPProtocol
# Import any other necessary modules like SessionManager or TankPool if their actual instances are needed
# For unit testing udp_handler, we might not need their full functionality if we focus on message processing.

class TestGameUdpHandler(unittest.TestCase):

    def setUp(self):
        # Create an instance of the protocol
        self.protocol = GameUDPProtocol()
        # Mock the transport
        self.transport = MagicMock()
        self.protocol.transport = self.transport # Assign the mock transport to the protocol instance
        self.addr = ('127.0.0.1', 12345)

    def test_empty_message_after_strip(self):
        """Test that an empty message (after stripping whitespace) is ignored and logged."""
        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(b'  \t\r\n  ', self.addr)
        
        self.transport.sendto.assert_not_called()
        mock_logger.warning.assert_called_once_with(
            f"Received empty message from {self.addr} after strip. Ignoring."
        )

    def test_invalid_json_udp(self):
        """Test that invalid JSON data results in an error response."""
        malformed_json_data = b'{this is not json'
        
        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(malformed_json_data, self.addr)

        expected_response = {"status": "error", "message": "Invalid JSON format"}
        expected_response_bytes = json.dumps(expected_response).encode('utf-8')
        
        self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
        # Check that an error was logged (the exact message might vary based on implementation)
        self.assertTrue(mock_logger.error.called)
        # Example of checking a specific part of the log message:
        logged_error_message = mock_logger.error.call_args[0][0]
        self.assertIn(f"Невалидный JSON получен от {self.addr}", logged_error_message)
        self.assertIn(malformed_json_data.decode('utf-8', errors='ignore'), logged_error_message)


    def test_unicode_decode_error_udp(self):
        """Test that data with invalid UTF-8 results in an encoding error response."""
        invalid_utf8_data = b'\xff\xfe\xfd{abc' # Invalid UTF-8 sequence
        
        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(invalid_utf8_data, self.addr)

        expected_response = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        expected_response_bytes = json.dumps(expected_response).encode('utf-8')
        
        self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
        self.assertTrue(mock_logger.error.called)
        logged_error_message = mock_logger.error.call_args[0][0]
        self.assertIn(f"Unicode decoding error from {self.addr}", logged_error_message)
        self.assertIn(f"Raw data: {invalid_utf8_data!r}", logged_error_message)

    def test_unknown_action_udp(self):
        """Test that a message with an unknown action results in an error response."""
        unknown_action_data = {"action": "fly_to_moon", "player_id": "player_test_unknown"}
        unknown_action_bytes = json.dumps(unknown_action_data).encode('utf-8')

        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(unknown_action_bytes, self.addr)

        expected_response = {"status": "error", "message": "Unknown action"}
        expected_response_bytes = json.dumps(expected_response).encode('utf-8')

        self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
        self.assertTrue(mock_logger.warning.called)
        # Example: logger.warning(f"Неизвестное действие '{action}' от игрока {player_id} ({addr}). Сообщение: {message_str}")
        logged_warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn(f"Неизвестное действие 'fly_to_moon' от игрока player_test_unknown ({self.addr})", logged_warning_message)

    def test_missing_player_id_udp(self):
        """Test that a message missing player_id (for actions that require it) is ignored."""
        missing_player_id_data = {"action": "join_game"} # player_id is missing
        missing_player_id_bytes = json.dumps(missing_player_id_data).encode('utf-8')

        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(missing_player_id_bytes, self.addr)
        
        self.transport.sendto.assert_not_called() # Should not send a response, just log
        self.assertTrue(mock_logger.warning.called)
        # Example: logger.warning(f"Нет player_id в сообщении от {addr}. Сообщение: '{message_str}'. Игнорируется.")
        logged_warning_message = mock_logger.warning.call_args[0][0]
        self.assertIn(f"Нет player_id в сообщении от {self.addr}", logged_warning_message)

if __name__ == '__main__':
    unittest.main()
