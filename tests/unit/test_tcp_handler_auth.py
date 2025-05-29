# tests/unit/test_tcp_handler_auth.py
# This file contains unit tests for the authentication server's TCP handler
# (auth_server.tcp_handler.handle_auth_client).
# Tests verify various client-server interaction scenarios,
# including successful and failed logins, and handling of incorrect requests.

import asyncio
import json # For working with JSON messages
import unittest
from unittest.mock import AsyncMock, patch, call # Mocking tools

# Import the function to be tested
from auth_server.tcp_handler import handle_auth_client
# MOCK_USERS_DB is not directly used here as authenticate_user is mocked.

class TestAuthTcpHandler(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for the authentication server's TCP handler.
    Uses `unittest.IsolatedAsyncioTestCase` for asynchronous tests.
    """

    async def test_successful_login(self):
        """
        Test successful user login.
        Checks that with correct credentials, the server returns
        a success message and the corresponding session token/message.
        """
        reader = AsyncMock(spec=asyncio.StreamReader) 
        writer = AsyncMock(spec=asyncio.StreamWriter) 
        writer.is_closing.return_value = False # Simulate that the writer is open
        
        login_request = {"action": "login", "username": "player1", "password": "password123"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        # Mock authenticate_user to return a successful result with an English message
        # The tcp_handler uses the second element of the tuple as both message and session_id in success case
        auth_response_message = "User player1 authenticated successfully."
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(True, auth_response_message))) as mock_auth_user:
            await handle_auth_client(reader, writer) 

        mock_auth_user.assert_called_once_with("player1", "password123")
        
        expected_response = {"status": "success", "message": auth_response_message, "session_id": auth_response_message}
        
        self.assertTrue(writer.write.called, "writer.write was not called.")
        actual_call_args_bytes = writer.write.call_args[0][0]
        
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response, "Server response does not match expected.")
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'), "Server response should end with a newline.")
        writer.drain.assert_called_once() 
        writer.close.assert_called_once() 
        writer.wait_closed.assert_called_once() 


    async def test_failed_login_wrong_password(self):
        """
        Test failed user login due to incorrect password.
        Checks that the server returns a failure message.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        login_request = {"action": "login", "username": "player1", "password": "wrongpassword"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        # Mock authenticate_user to return "Incorrect password."
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(False, "Incorrect password."))) as mock_auth_user:
            await handle_auth_client(reader, writer)

        mock_auth_user.assert_called_once_with("player1", "wrongpassword")
        expected_response = {"status": "failure", "message": "Authentication failed: Incorrect password."}
        
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    async def test_failed_login_user_not_found(self):
        """
        Test failed user login because the user was not found.
        Checks that the server returns an appropriate failure message.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        login_request = {"action": "login", "username": "nonexistentuser", "password": "anypassword"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        # Mock authenticate_user to return "User not found."
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(False, "User not found."))) as mock_auth_user:
            await handle_auth_client(reader, writer)

        mock_auth_user.assert_called_once_with("nonexistentuser", "anypassword")
        expected_response = {"status": "failure", "message": "Authentication failed: User not found."}
        
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()


    async def test_invalid_json_format(self):
        """
        Test handling of a request with an invalid JSON format.
        Checks that the server returns an error for invalid JSON.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        malformed_json_request = b'{"action": "login, "username": "player1"}\n' # Invalid JSON
        reader.readuntil.return_value = malformed_json_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid JSON format"}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    async def test_unicode_decode_error(self):
        """
        Test handling of a request with a Unicode decode error (not UTF-8).
        Checks that the server returns an error for invalid character encoding.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False

        invalid_utf8_request = b'\xff\xfe\xfd{"action": "login"}\n' # Invalid UTF-8 sequence
        reader.readuntil.return_value = invalid_utf8_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    async def test_unknown_action(self):
        """
        Test handling of a request with an unknown action.
        Checks that the server returns an error for an unknown action.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False 

        unknown_action_request = {"action": "unknown_action", "username": "player1"}
        reader.readuntil.return_value = (json.dumps(unknown_action_request) + '\n').encode('utf-8')

        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock()) as mock_auth_user:
            await handle_auth_client(reader, writer)
        
        mock_auth_user.assert_not_called() 
        expected_response = {"status": "error", "message": "Unknown or missing action"}
        actual_call_args_bytes = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args_bytes.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args_bytes.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

    @patch('auth_server.tcp_handler.logger')
    @patch('auth_server.tcp_handler.ACTIVE_CONNECTIONS_AUTH')
    @patch('auth_server.tcp_handler.SUCCESSFUL_AUTHS') # SUCCESSFUL_AUTHS is not used in this path
    @patch('auth_server.tcp_handler.FAILED_AUTHS')   # FAILED_AUTHS is not used in this path
    async def test_empty_message_just_newline(
            self,
            MockFailedAuths, # Unused due to path
            MockSuccessfulAuths, # Unused due to path
            MockActiveConnections,
            mock_logger
    ):
        '''Tests handling of an empty message (only newline character).'''
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.is_closing.return_value = False 

        mock_reader.readuntil.side_effect = [
            b'\n', # First call returns just newline
            asyncio.IncompleteReadError(b'', 0) # Second call to exit loop
        ]
        
        await handle_auth_client(mock_reader, mock_writer)

        expected_response_json = {
            "status": "error",
            "message": "Empty message or only newline character received"
        }
        expected_response_bytes = json.dumps(expected_response_json).encode('utf-8') + b'\n'
        
        mock_writer.write.assert_any_call(expected_response_bytes)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once() 

        mock_logger.warning.assert_any_call("Empty message or only newline character received from ('127.0.0.1', 12345). Sending error and closing.")
        MockActiveConnections.inc.assert_called_once()
        MockActiveConnections.dec.assert_called_once() 

    async def test_no_data_from_client(self):
        """
        Test situation where client sends no data (connection closes or EOF).
        Server should send an error response for empty message.
        """
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.is_closing.return_value = False
        
        reader.readuntil.return_value = b'' # Simulate connection close or no data before EOF

        await handle_auth_client(reader, writer)

        expected_response_json = {
            "status": "error",
            "message": "Empty message or only newline character received" 
        }
        expected_response_bytes = json.dumps(expected_response_json).encode('utf-8') + b'\n'
        
        writer.write.assert_called_once_with(expected_response_bytes)
        writer.drain.assert_called_once() 
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()

if __name__ == '__main__':
    unittest.main()
