# tests/unit/test_udp_handler_game.py
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch, call

from game_server.udp_handler import GameUDPProtocol
# Исправленный импорт: SessionManager и GameSession
from game_server.session_manager import SessionManager, GameSession
from game_server.tank_pool import TankPool
from game_server.tank import Tank


@patch('game_server.udp_handler.publish_rabbitmq_message')
class TestGameUDPHandlerRabbitMQ(unittest.TestCase):

    def setUp(self):
        self.protocol = GameUDPProtocol()
        self.mock_transport = MagicMock()
        self.protocol.transport = self.mock_transport

        self.protocol.session_manager = MagicMock(spec=SessionManager)
        self.protocol.tank_pool = MagicMock(spec=TankPool)

    def test_datagram_received_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq):
        addr = ('127.0.0.1', 1234)
        player_id = "player1"
        tank_id = "tank_A"

        mock_session = MagicMock(spec=GameSession)  # Используем GameSession для spec, если нужно
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session

        mock_tank = MagicMock(spec=Tank)
        mock_tank.tank_id = tank_id
        # self.protocol.tank_pool.get_tank.return_value = mock_tank # Эта строка была закомментирована в вашем логе, оставляю так

        message_data = {
            "action": "shoot",
            "player_id": player_id
        }
        message_bytes = json.dumps(message_data).encode('utf-8')

        self.protocol.datagram_received(message_bytes, addr)

        expected_mq_message = {
            "player_id": player_id,
            "command": "shoot",
            "details": {
                "source": "udp_handler",
                "tank_id": tank_id
            }
        }

        mock_publish_rabbitmq.assert_called_once_with(
            '',
            'player_commands',
            expected_mq_message
        )

    def test_datagram_received_move_command_direct_execution_no_rabbitmq(self, mock_publish_rabbitmq):
        addr = ('127.0.0.1', 1234)
        player_id = "player2"
        tank_id = "tank_B"
        new_position = [50, 50]

        mock_session = MagicMock(spec=GameSession)  # Используем GameSession для spec
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        mock_session.get_tanks_state = MagicMock(
            return_value=[{"id": tank_id, "position": new_position, "health": 100}])
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session

        mock_tank = MagicMock(spec=Tank)
        # Убедимся, что get_tank возвращает наш мок танка, если он вызывается
        self.protocol.tank_pool.get_tank.return_value = mock_tank

        message_data = {
            "action": "move",
            "player_id": player_id,
            "position": new_position
        }
        message_bytes = json.dumps(message_data).encode('utf-8')

        self.protocol.datagram_received(message_bytes, addr)

        mock_publish_rabbitmq.assert_not_called()
        mock_tank.move.assert_called_once_with(tuple(new_position))
        self.protocol.transport.sendto.assert_called()

    def test_datagram_received_join_game_no_rabbitmq(self, mock_publish_rabbitmq):
        addr = ('127.0.0.1', 1234)
        player_id = "player3"

        acquired_tank_mock = MagicMock(spec=Tank)
        acquired_tank_mock.tank_id = "tank_C"
        acquired_tank_mock.get_state.return_value = {"id": "tank_C", "position": (0, 0), "health": 100}
        self.protocol.tank_pool.acquire_tank.return_value = acquired_tank_mock

        # Исправлено: используется spec=GameSession
        mock_session_instance = MagicMock(spec=GameSession)
        mock_session_instance.session_id = "session_new"
        mock_session_instance.get_players_count.return_value = 0

        self.protocol.session_manager.get_session_by_player_id.return_value = None
        self.protocol.session_manager.sessions = {}
        # Убеждаемся, что create_session возвращает наш мок
        self.protocol.session_manager.create_session.return_value = mock_session_instance

        message_data = {"action": "join_game", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')

        self.protocol.datagram_received(message_bytes, addr)

        mock_publish_rabbitmq.assert_not_called()
        self.protocol.transport.sendto.assert_called()


if __name__ == '__main__':
    unittest.main()