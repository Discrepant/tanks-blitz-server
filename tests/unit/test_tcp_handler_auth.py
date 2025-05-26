import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch, call

from auth_server.tcp_handler import handle_auth_client
# Assuming MOCK_USERS_DB is accessible for reference or we mock authenticate_user fully
# from auth_server.user_service import MOCK_USERS_DB

class TestAuthTcpHandler(unittest.IsolatedAsyncioTestCase):

    async def test_successful_login(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        
        login_request = {"action": "login", "username": "player1", "password": "password123"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(True, "User player1 successfully authenticated."))) as mock_auth_user:
            await handle_auth_client(reader, writer)

        mock_auth_user.assert_called_once_with("player1", "password123")
        
        expected_response = {"status": "success", "message": "User player1 successfully authenticated.", "session_id": "User player1 successfully authenticated."}
        
        # Check that writer.write was called
        self.assertTrue(writer.write.called)
        # Get the first call's arguments
        actual_call_args = writer.write.call_args[0][0]
        
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()


    async def test_failed_login_wrong_password(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)

        login_request = {"action": "login", "username": "player1", "password": "wrongpassword"}
        reader.readuntil.return_value = (json.dumps(login_request) + '\n').encode('utf-8')

        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock(return_value=(False, "Invalid password."))) as mock_auth_user:
            await handle_auth_client(reader, writer)

        mock_auth_user.assert_called_once_with("player1", "wrongpassword")
        expected_response = {"status": "failure", "message": "Authentication failed: Invalid password."}
        
        actual_call_args = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()


    async def test_invalid_json_format(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)

        # Malformed JSON: missing quote after "login"
        malformed_json_request = b'{"action": "login, "username": "player1"}\n'
        reader.readuntil.return_value = malformed_json_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid JSON format"}
        actual_call_args = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()

    async def test_unicode_decode_error(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)

        # Invalid UTF-8 sequence
        invalid_utf8_request = b'\xff\xfe\xfd{"action": "login"}\n'
        reader.readuntil.return_value = invalid_utf8_request

        await handle_auth_client(reader, writer)

        expected_response = {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
        actual_call_args = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()

    async def test_unknown_action(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)

        unknown_action_request = {"action": "unknown_action", "username": "player1"}
        reader.readuntil.return_value = (json.dumps(unknown_action_request) + '\n').encode('utf-8')

        # We still patch authenticate_user, though it shouldn't be called.
        with patch('auth_server.tcp_handler.authenticate_user', AsyncMock()) as mock_auth_user:
            await handle_auth_client(reader, writer)
        
        mock_auth_user.assert_not_called()
        expected_response = {"status": "error", "message": "Unknown or missing action"}
        actual_call_args = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()

    async def test_empty_message_just_newline(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        
        reader.readuntil.return_value = b'\n' # Simulates client sending only a newline

        await handle_auth_client(reader, writer)

        # This should result in an "Empty message received" error because a newline becomes an empty string after strip
        expected_response = {"status": "error", "message": "Empty message received"}
        actual_call_args = writer.write.call_args[0][0]
        self.assertEqual(json.loads(actual_call_args.decode('utf-8').strip()), expected_response)
        self.assertTrue(actual_call_args.endswith(b'\n'))
        writer.drain.assert_called_once()
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()

    async def test_no_data_from_client(self):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        
        reader.readuntil.return_value = b'' # Simulates connection closed or no data sent before EOF

        await handle_auth_client(reader, writer)

        # No response should be written if no data is received
        writer.write.assert_not_called()
        # Still, the connection should be closed
        writer.close.assert_called_once()
        await writer.wait_closed.assert_called_once()

if __name__ == '__main__':
    unittest.main()
