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

    def test_datagram_received_empty_json_payload(self):
        """Test messages that result in an empty payload after processing."""
        test_cases = [
            (b'  \t\r\n  ', "whitespace only"), 
            (b'\n', "newline only"),
            (b'\x00\x00\x00', "null bytes only"),
            (b' \x00 \n ', "mixed whitespace and nulls")
        ]
        expected_response_dict = {"status": "error", "message": "Empty JSON payload"}
        expected_response_bytes = json.dumps(expected_response_dict).encode('utf-8')

        for data_bytes, case_name in test_cases:
            with self.subTest(case_name=case_name):
                self.transport.reset_mock() # Reset mocks for each subtest
                with patch('game_server.udp_handler.logger') as mock_logger:
                    self.protocol.datagram_received(data_bytes, self.addr)
                
                self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
                
                # Verify the log message
                # Expected log: f"Empty message after decoding, stripping, and cleaning from {addr}. Original string: '{decoded_payload_str}', Original bytes: {data!r}"
                self.assertTrue(mock_logger.warning.called)
                logged_warning_args = mock_logger.warning.call_args[0]
                self.assertIn(f"Empty message after decoding, stripping, and cleaning from {self.addr}", logged_warning_args[0])
                # The decoded_payload_str would be data_bytes.decode('utf-8', errors='replace' or similar)
                # For simplicity here, we'll just check that the raw bytes are mentioned.
                self.assertIn(f"Original bytes: {data_bytes!r}", logged_warning_args[0])


    def test_datagram_received_invalid_json_valid_utf8(self):
        """Test that valid UTF-8 data which is not valid JSON results in an error response."""
        malformed_json_data = b'{this is not json' # Valid UTF-8, but not JSON
        
        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(malformed_json_data, self.addr)

        expected_response = {"status": "error", "message": "Invalid JSON format"}
        expected_response_bytes = json.dumps(expected_response).encode('utf-8')
        
        self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
        self.assertTrue(mock_logger.error.called)
        # Expected log: f"Invalid JSON received from {addr}: '{processed_payload_str}' | Error: {jde}. Raw bytes: {data!r}"
        logged_error_args = mock_logger.error.call_args[0]
        self.assertIn(f"Invalid JSON received from {self.addr}", logged_error_args[0])
        # The processed_payload_str would be malformed_json_data.decode().strip().replace('\x00', '')
        self.assertIn(f"'{malformed_json_data.decode('utf-8',errors='ignore').strip()}'", logged_error_args[0])
        self.assertIn(f"Raw bytes: {malformed_json_data!r}", logged_error_args[0])


    def test_datagram_received_invalid_utf8(self):
        """Test that data with invalid UTF-8 results in an encoding error response."""
        invalid_utf8_data = b'\xff\xfe\xfd{abc' # Invalid UTF-8 sequence
        
        with patch('game_server.udp_handler.logger') as mock_logger:
            self.protocol.datagram_received(invalid_utf8_data, self.addr)

        expected_response = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        expected_response_bytes = json.dumps(expected_response).encode('utf-8')
        
        self.transport.sendto.assert_called_once_with(expected_response_bytes, self.addr)
        self.assertTrue(mock_logger.error.called)
        # Expected log: f"Unicode decoding error from {addr}: {ude}. Raw data: {data!r}"
        logged_error_args = mock_logger.error.call_args[0]
        self.assertIn(f"Unicode decoding error from {self.addr}", logged_error_args[0])
        self.assertIn(f"Raw data: {invalid_utf8_data!r}", logged_error_args[0])

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
