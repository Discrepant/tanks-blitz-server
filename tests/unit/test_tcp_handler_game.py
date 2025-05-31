# tests/unit/test_tcp_handler_game.py
# Этот файл содержит модульные тесты для TCP-обработчика игрового сервера
# (game_server.tcp_handler.handle_game_client).
# Основное внимание уделяется проверке корректности публикации команд в RabbitMQ.

import logging
# Настройка базового логирования для тестов. Помогает отслеживать ход выполнения тестов.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')

import asyncio
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock # Инструменты для мокирования

# Импортируем тестируемую функцию
from game_server.tcp_handler import handle_game_client 
# Предполагается, что Player и GameRoom либо более сложны и тестируются отдельно,
# либо их поведение полностью мокируется в этих тестах.
# Фокус здесь на проверке взаимодействия с RabbitMQ (через mock_publish_rabbitmq).
# from game_server.game_logic import Player, GameRoom # Закомментировано, так как используются моки

class MockPlayer:
    """
    Упрощенный мок-класс для Player.
    Используется для имитации объекта игрока в тестах TCP-обработчика.
    Содержит основные атрибуты и асинхронный метод send_message.
    """
    def __init__(self, writer, name="test_player", token="test_token", id="mock_player_id"): # Added id parameter
        self.writer = writer # Объект StreamWriter для отправки сообщений игроку
        self.name = name # Имя игрока
        self.token = token # Токен сессии игрока
        self.id = id # ID игрока, добавлен для тестов
        self.address = ("127.0.0.1", 12345) # Пример адреса клиента

    async def send_message(self, message: str):
        """
        Асинхронно отправляет сообщение игроку.
        Имитирует поведение реального метода Player.send_message.
        """
        if self.writer and not self.writer.is_closing(): # Если writer существует и не закрывается
            self.writer.write(message.encode('utf-8') + b"\n") # Отправляем сообщение с новой строкой
            await self.writer.drain() # Ожидаем сброса буфера

# Используем AsyncMock для publish_rabbitmq_message, так как это асинхронная функция.
# new_callable=AsyncMock гарантирует, что мок будет асинхронным.
@patch('game_server.tcp_handler.publish_rabbitmq_message', new_callable=AsyncMock)
class TestGameTCPHandlerRabbitMQ(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для проверки взаимодействия TCP-обработчика игрового сервера с RabbitMQ.
    Проверяет, что команды, полученные от клиента, корректно публикуются в очередь RabbitMQ.
    """

    async def test_handle_game_client_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: команда SHOOT, полученная от клиента, публикуется в RabbitMQ.
        Имитирует успешную последовательность логина, затем команду SHOOT.
        Проверяет, что `publish_rabbitmq_message` вызывается с правильными аргументами.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader) # Мок для StreamReader
        mock_writer = AsyncMock(spec=asyncio.StreamWriter) # Мок для StreamWriter
        mock_writer.is_closing.return_value = False # Writer открыт
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345) # Адрес клиента
        
        # Имитируем последовательность команд от клиента: LOGIN, затем SHOOT, затем разрыв соединения
        login_command = "LOGIN test_user test_pass\n"
        shoot_command = "SHOOT\n"
        mock_reader.readuntil.side_effect = [ # Задаем последовательность возвращаемых значений для readuntil
            login_command.encode('utf-8'),  # Ответ на первый вызов (LOGIN)
            shoot_command.encode('utf-8'),  # Ответ на второй вызов (SHOOT)
            ConnectionResetError()          # Имитируем разрыв соединения для выхода из цикла в handle_game_client
        ]

        mock_game_room = MagicMock() # Мок для GameRoom
        # Мокируем authenticate_player для возврата успешного результата и мок-игрока
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        # Мокируем add_player
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() # Мок для remove_player, вызываемого в finally

        # Мокируем создание экземпляра Player внутри handle_game_client.
        # В этом тесте предполагается, что GameRoom возвращает уже аутентифицированный объект игрока,
        # или что Player создается внутри tcp_handler после успешной аутентификации.
        # Судя по структуре tcp_handler, Player создается после аутентификации.
        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance) as mock_player_class_constructor:
            await handle_game_client(mock_reader, mock_writer, mock_game_room) # Вызываем тестируемый обработчик

        # Ожидаемое сообщение для публикации в RabbitMQ
        expected_message_shoot = {
            "player_id": "test_user",
            "command": "shoot",
            "details": {"source": "tcp_handler"} # Дополнительная информация об источнике команды
        }
        # Проверяем, что publish_rabbitmq_message был вызван с командой SHOOT
        await asyncio.sleep(0) # Даем возможность выполниться асинхронным задачам (если они есть)
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_shoot) # Проверяем вызов
        
        # Проверяем, что клиенту было отправлено подтверждение получения команды (приблизительная проверка)
        await asyncio.sleep(0) # Снова даем время на выполнение задач
        # Собираем все данные, которые были записаны в writer
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"COMMAND_RECEIVED SHOOT\n", written_data, "Клиент не получил подтверждение команды SHOOT.")

    async def test_handle_game_client_move_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: команда MOVE, полученная от клиента, публикуется в RabbitMQ.
        Имитирует успешный логин, затем команду MOVE с координатами.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        move_command = "MOVE 10 20\n" # Команда MOVE с координатами X=10, Y=20
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            move_command.encode('utf-8'),
            ConnectionResetError() # Для выхода из цикла
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        # Ожидаемое сообщение для RabbitMQ
        expected_message_move = {
            "player_id": "test_user",
            "command": "move",
            "details": {"new_position": [10, 20]} # Ожидаемые координаты
        }
        await asyncio.sleep(0) # Даем время на выполнение
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_move) # Проверяем вызов
        
        await asyncio.sleep(0) # Даем время на выполнение
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"COMMAND_RECEIVED MOVE\n", written_data, "Клиент не получил подтверждение команды MOVE.")

    async def test_handle_game_client_unknown_command(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: неизвестная команда от клиента не публикуется в RabbitMQ,
        и клиенту отправляется сообщение UNKNOWN_COMMAND.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        unknown_command = "JUMP\n" # Неизвестная команда
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            unknown_command.encode('utf-8'),
            ConnectionResetError()
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Login OK", "token123"))
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() # Добавляем мок для remove_player
        
        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) # Даем время
        # Проверяем, что publish_rabbitmq_message НЕ был вызван для неизвестной команды
        mock_publish_rabbitmq.assert_not_called() 
        
        await asyncio.sleep(0) # Даем время
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        # Проверяем, что было отправлено сообщение UNKNOWN_COMMAND
        self.assertIn(b"UNKNOWN_COMMAND\n", written_data, "Клиент не получил сообщение UNKNOWN_COMMAND.")

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую
    unittest.main()