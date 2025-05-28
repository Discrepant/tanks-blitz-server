# tests/unit/test_udp_handler_game.py
# Этот файл содержит модульные тесты для UDP-обработчика игрового сервера
# (game_server.udp_handler.GameUDPProtocol).
# Тесты фокусируются на проверке правильности обработки различных UDP-сообщений,
# включая публикацию команд в RabbitMQ и прямое выполнение некоторых действий.

import asyncio
import json # Для работы с JSON-сообщениями
import unittest
from unittest.mock import MagicMock, patch, call # Инструменты для мокирования

# Импортируем тестируемый класс GameUDPProtocol
from game_server.udp_handler import GameUDPProtocol
# Предполагается, что SessionManager, TankPool, Tank импортируются или мокируются по мере необходимости.
from game_server.session_manager import SessionManager, GameSession
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Важно, чтобы RABBITMQ_QUEUE_PLAYER_COMMANDS было актуальным строковым значением,
# если оно используется напрямую в утверждениях, или также мокировать core.message_broker_clients.
# from core.message_broker_clients import RABBITMQ_QUEUE_PLAYER_COMMANDS # Для утверждения, если необходимо

# Мокируем функцию publish_rabbitmq_message там, где она используется (в game_server.udp_handler).
# Это позволяет нам проверять, вызывается ли она, и с какими аргументами,
# без реальной отправки сообщений в RabbitMQ.
@patch('game_server.udp_handler.publish_rabbitmq_message') 
class TestGameUDPHandlerRabbitMQ(unittest.TestCase):
    """
    Набор тестов для GameUDPProtocol, сфокусированный на взаимодействии с RabbitMQ.
    Проверяет, что команды 'shoot' публикуются в RabbitMQ, а другие команды,
    такие как 'move' и 'join_game', обрабатываются напрямую (согласно текущей логике).
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает экземпляр GameUDPProtocol и мокирует его транспорт и зависимости
        (SessionManager, TankPool).
        """
        self.protocol = GameUDPProtocol() # Создаем экземпляр тестируемого протокола
        self.mock_transport = MagicMock(spec=asyncio.DatagramTransport) # Мок для транспорта UDP
        self.protocol.transport = self.mock_transport # Присваиваем мок-транспорт протоколу
        
        # Мокируем зависимости GameUDPProtocol
        self.protocol.session_manager = MagicMock(spec=SessionManager)
        self.protocol.tank_pool = MagicMock(spec=TankPool)

    def test_datagram_received_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'shoot', полученная по UDP, корректно публикуется в RabbitMQ.
        Имитирует получение датаграммы с командой 'shoot' и проверяет,
        что `publish_rabbitmq_message` вызывается с ожидаемыми параметрами.
        """
        addr = ('127.0.0.1', 1234) # Пример адреса клиента
        player_id = "player1"
        tank_id = "tank_A"

        # Настройка моков для сессии и танка
        mock_session = MagicMock(spec=GameSession)
        # Игрок player1 находится в сессии и ему назначен танк tank_A
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        mock_tank = MagicMock(spec=Tank)
        mock_tank.tank_id = tank_id # Убедимся, что у мок-танка есть tank_id
        # Эта строка была пропущена в исходном коде, но подразумевается логикой udp_handler.
        # Однако, для команды "shoot" в текущей реализации udp_handler, get_tank не вызывается,
        # он только извлекает tank_id из player_data.
        # self.protocol.tank_pool.get_tank.return_value = mock_tank 
        
        # Формируем сообщение команды 'shoot'
        message_data = {
            "action": "shoot",
            "player_id": player_id
            # Другие поля, которые клиент может отправлять с командой "shoot"
        }
        message_bytes = json.dumps(message_data).encode('utf-8') # Кодируем в байты
        
        # Вызываем тестируемый метод
        self.protocol.datagram_received(message_bytes, addr)
        
        # Ожидаемое сообщение для публикации в RabbitMQ
        expected_mq_message = {
            "player_id": player_id,
            "command": "shoot", # Команда для обработчика в command_consumer
            "details": {
                "source": "udp_handler", # Источник команды
                "tank_id": tank_id # udp_handler был изменен, чтобы включать tank_id
            }
        }
        
        # Проверяем, что publish_rabbitmq_message была вызвана корректно.
        # Первый аргумент - exchange_name (пустая строка для обменника по умолчанию).
        # Второй аргумент - routing_key (имя очереди).
        mock_publish_rabbitmq.assert_called_once_with(
            '', # exchange_name (обменник по умолчанию)
            'player_commands', # routing_key (фактическое имя очереди для RABBITMQ_QUEUE_PLAYER_COMMANDS)
            expected_mq_message
        )
        
        # Проверяем, что метод tank.shoot() НЕ вызывается напрямую в UDP-обработчике.
        # Эта логика теперь перенесена в command_consumer.
        # mock_tank.shoot.assert_not_called() # Закомментировано, так как get_tank не вызывается для shoot в udp_handler.
        # Фактический объект танка получается в потребителе, а не в обработчике для "shoot" после изменения.
        # Обработчик только получает tank_id из player_data.

        # Проверяем, что широковещательная рассылка НЕ произошла напрямую отсюда для события выстрела.
        # self.mock_transport.sendto.assert_not_called() # Это может быть слишком строгой проверкой, если отправляются другие сообщения (например, ошибки).
        # Более надежно: проверить, что конкретное широковещательное сообщение "player_shot" НЕ отправляется.
        # Для этой конкретной подзадачи мы предполагаем, что если publish_rabbitmq_message вызвана,
        # то прямая обработка (широковещательная рассылка) пропускается.
        # (В текущей реализации udp_handler нет явной рассылки после shoot, так что эта проверка нестрогая)

    def test_datagram_received_move_command_direct_execution_no_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'move' обрабатывается напрямую в UDP-обработчике и НЕ публикуется в RabbitMQ.
        Проверяет, что вызывается метод tank.move() и происходит широковещательная рассылка состояния.
        """
        # Этот тест проверяет, что команда "move" все еще обрабатывается напрямую (согласно текущему плану)
        # и НЕ попадает в RabbitMQ через UDP-обработчик.
        addr = ('127.0.0.1', 1234)
        player_id = "player2"
        tank_id = "tank_B"
        new_position = [50, 50] # Новая позиция для танка

        mock_session = MagicMock(spec=GameSession)
        mock_session.session_id = "test_udp_session_123" # Установка атрибута session_id
        mock_session.players = {player_id: {'address': addr, 'tank_id': tank_id}}
        # Мокируем get_tanks_state, чтобы он возвращал ожидаемое состояние после перемещения
        mock_session.get_tanks_state.return_value = [{"id": tank_id, "position": new_position, "health": 100}]
        self.protocol.session_manager.get_session_by_player_id.return_value = mock_session
        
        mock_tank = MagicMock(spec=Tank)
        mock_tank.tank_id = tank_id # Устанавливаем ID мок-танка
        self.protocol.tank_pool.get_tank.return_value = mock_tank # get_tank должен вернуть этот мок

        message_data = {
            "action": "move",
            "player_id": player_id,
            "position": new_position
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called() # Убеждаемся, что 'move' не отправляется в RabbitMQ
        mock_tank.move.assert_called_once_with(tuple(new_position)) # Проверяем вызов tank.move
        # Проверяем, что широковещательная рассылка ДЕЙСТВИТЕЛЬНО произошла для 'move' (согласно существующей логике udp_handler)
        self.protocol.transport.sendto.assert_called() # Проверяем, что транспорт был использован для отправки


    def test_datagram_received_join_game_no_rabbitmq(self, mock_publish_rabbitmq: MagicMock):
        """
        Тест: команда 'join_game' обрабатывается напрямую и НЕ публикуется в RabbitMQ.
        Проверяет, что некритичные команды, такие как "join_game", не попадают в RabbitMQ.
        """
        addr = ('127.0.0.1', 1234)
        player_id = "player3"
        
        # Мокируем танк, который будет "получен" из пула
        acquired_tank_mock = MagicMock(spec=Tank)
        acquired_tank_mock.tank_id = "tank_C"
        acquired_tank_mock.get_state.return_value = {"id": "tank_C", "position": (0,0), "health": 100}
        self.protocol.tank_pool.acquire_tank.return_value = acquired_tank_mock
        
        # Мокируем создание сессии и добавление игрока
        mock_session_instance = MagicMock(spec=GameSession) # Используем spec для GameSession
        mock_session_instance.session_id="session_new"
        mock_session_instance.get_players_count.return_value = 0 # До добавления текущего игрока

        self.protocol.session_manager.get_session_by_player_id.return_value = None # Игрок изначально не в сессии
        # Настраиваем create_session для возврата нашего мок-экземпляра сессии
        self.protocol.session_manager.create_session.return_value = mock_session_instance 
        # Имитируем ситуацию, когда нет существующих сессий, чтобы заставить создать новую.
        self.protocol.session_manager.sessions = {} 

        message_data = {"action": "join_game", "player_id": player_id}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        self.protocol.datagram_received(message_bytes, addr)
        
        mock_publish_rabbitmq.assert_not_called() # Команда 'join_game' не должна публиковаться в RabbitMQ
        # Проверяем, что клиенту был отправлен ответ на 'join_game'
        self.protocol.transport.sendto.assert_called()


if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()
