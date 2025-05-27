# tests/unit/test_tcp_handler_game.py
import asyncio
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock

from game_server.tcp_handler import handle_game_client

# Mock Player class for testing
class MockPlayer:
    def __init__(self, writer, name="test_player", token="test_token"):
        self.writer = writer
        self.name = name
        self.token = token
        self.address = ("127.0.0.1", 12345) # Mock address

    async def send_message(self, message):
        if self.writer and not self.writer.is_closing():
            self.writer.write(message.encode() + b"\n")
            await self.writer.drain()

@patch('game_server.tcp_handler.publish_rabbitmq_message')
class TestGameTCPHandlerRabbitMQ(unittest.IsolatedAsyncioTestCase):

    async def test_handle_game_client_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        shoot_command = "SHOOT\n"
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            shoot_command.encode('utf-8'),
            ConnectionResetError() # Используем ConnectionResetError для завершения
        ]

        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock()
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) # Даем время асинхронным задачам
        expected_message_shoot = {
            "player_id": "test_user",
            "command": "shoot",
            "details": {"source": "tcp_handler"}
        }
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_shoot)

        await asyncio.sleep(0) # Даем время асинхронным задачам
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"COMMAND_ACKNOWLEDGED\n", written_data)


    async def test_handle_game_client_move_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        move_command = "MOVE 10 20\n"
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            move_command.encode('utf-8'),
            ConnectionResetError() # Используем ConnectionResetError для завершения
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock()
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) # Даем время асинхронным задачам
        expected_message_move = {
            "player_id": "test_user",
            "command": "move",
            "details": {"new_position": [10, 20], "source": "tcp_handler"}
        }
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_move)

        await asyncio.sleep(0) # Даем время асинхронным задачам
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"COMMAND_ACKNOWLEDGED\n", written_data)

    async def test_handle_game_client_unknown_command(self, mock_publish_rabbitmq):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        unknown_command = "JUMP\n"
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            unknown_command.encode('utf-8'),
            ConnectionResetError() # Используем ConnectionResetError для завершения
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock()
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) # Даем время асинхронным задачам
        mock_publish_rabbitmq.assert_not_called()

        await asyncio.sleep(0) # Даем время асинхронным задачам
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"UNKNOWN_COMMAND\n", written_data)

if __name__ == '__main__':
    unittest.main()