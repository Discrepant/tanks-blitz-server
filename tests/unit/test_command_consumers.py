# tests/unit/test_command_consumers.py
# Этот файл содержит модульные тесты для потребителей команд и событий из RabbitMQ,
# а именно для PlayerCommandConsumer и MatchmakingEventConsumer.
import unittest
from unittest.mock import MagicMock, patch, call # Инструменты для мокирования
import json # Для работы с JSON-сообщениями

# Предполагается, что структура проекта позволяет такой путь импорта.
# Если модули находятся в корне проекта или PYTHONPATH настроен иначе, путь может измениться.
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Примечание по использованию декораторов @patch:
# Порядок декораторов имеет значение. Если вы мокируете несколько объектов,
# они передаются в тестовый метод в порядке "снизу вверх" или "изнутри наружу".
# Например:
# @patch('A')
# @patch('B')
# def test_something(self, mock_B, mock_A): ...
#
# В данном файле декораторы на уровне класса были удалены и заменены
# контекстными менеджерами `with patch(...)` внутри каждого тестового метода.
# Это сделано для большей ясности и чтобы избежать проблем с порядком,
# особенно когда мокируется метод самого тестируемого класса (_connect_and_declare).

class TestPlayerCommandConsumer(unittest.TestCase):
    """
    Набор тестов для PlayerCommandConsumer.
    Проверяет логику обработки различных команд игрока, полученных из RabbitMQ.
    """

    @classmethod
    def setUpClass(cls):
        cls.mock_pika_patcher = patch('pika.BlockingConnection', autospec=True)
        cls.mock_BlockingConnection = cls.mock_pika_patcher.start()

        cls.mock_core_patcher = patch('core.message_broker_clients.get_rabbitmq_channel', autospec=True)
        cls.mock_get_rabbitmq_channel = cls.mock_core_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_pika_patcher.stop()
        cls.mock_core_patcher.stop()

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает мок-объекты для зависимостей (SessionManager, TankPool)
        и экземпляр PlayerCommandConsumer с этими моками.
        Также мокируется канал RabbitMQ.
        """
        # Сбрасываем состояние моков, созданных в setUpClass
        self.mock_BlockingConnection.reset_mock()
        self.mock_get_rabbitmq_channel.reset_mock()
        
        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        
        # Создаем экземпляр потребителя с мок-зависимостями.
        # _connect_and_declare будет мокирован в каждом тесте, чтобы избежать реального подключения.
        # Mocks for pika.BlockingConnection and get_rabbitmq_channel are already active via setUpClass.
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            self.consumer = PlayerCommandConsumer(
                session_manager=self.mock_session_manager,
                tank_pool=self.mock_tank_pool
            )
        # Канал RabbitMQ теперь будет предоставлен моком mock_get_rabbitmq_channel из setUpClass
        self.mock_channel = self.mock_get_rabbitmq_channel.return_value
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_shoot_command_success(self):
        """
        Тест успешной обработки команды 'shoot'.
        Проверяет, что вызываются методы поиска сессии, танка, выстрела танка
        и подтверждение сообщения RabbitMQ.
        """
        # _connect_and_declare мокируется для контроля над созданием экземпляра.
        # pika.BlockingConnection и get_rabbitmq_channel мокируются на уровне класса через setUpClass.
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            # For now, assume setUp's consumer is fine. If tests fail, we might need to re-init here.

            mock_tank_instance = MagicMock(spec=Tank) # Мок для объекта танка
            # Настраиваем мок-менеджер сессий, чтобы он возвращал мок-сессию
            self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
                players={"player1": {"tank_id": "tank123"}} # Данные игрока в сессии
            )
            # Настраиваем мок-пул танков, чтобы он возвращал наш мок-танк
            self.mock_tank_pool.get_tank.return_value = mock_tank_instance
            
            # Формируем тело сообщения команды
            message_body = json.dumps({
                "player_id": "player1",
                "command": "shoot",
                "details": {}
            })
            mock_method = MagicMock(delivery_tag=123) # Мок для информации о доставке RabbitMQ
            
            # Вызываем тестируемый callback-метод
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            # Проверяем, что были вызваны ожидаемые методы
            self.mock_session_manager.get_session_by_player_id.assert_called_once_with("player1")
            self.mock_tank_pool.get_tank.assert_called_once_with("tank123")
            mock_tank_instance.shoot.assert_called_once() # Метод shoot у танка должен быть вызван
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=123) # Сообщение должно быть подтверждено

    def test_callback_unknown_command(self):
        """
        Тест обработки неизвестной команды.
        Проверяет, что неизвестная команда корректно подтверждается (ack) и не вызывает ошибок.
        """
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
                players={"player1": {"tank_id": "tank123"}}
            )
            self.mock_tank_pool.get_tank.return_value = MagicMock(spec=Tank)
            message_body = json.dumps({"player_id": "player1", "command": "fly", "details": {}}) # Неизвестная команда "fly"
            mock_method = MagicMock(delivery_tag=125)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=125) # Сообщение подтверждается

    def test_callback_missing_player_id(self):
        """
        Тест обработки сообщения без player_id.
        Проверяет, что сообщение подтверждается и не вызывает ошибок.
        """
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            message_body = json.dumps({"command": "shoot", "details": {}}) # Отсутствует player_id
            mock_method = MagicMock(delivery_tag=126)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=126)

    def test_callback_player_not_in_session(self):
        """
        Тест обработки команды от игрока, который не найден в активной сессии.
        """
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            self.mock_session_manager.get_session_by_player_id.return_value = None # Игрок не в сессии
            message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
            mock_method = MagicMock(delivery_tag=127)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=127)

    def test_callback_tank_not_found(self):
        """
        Тест обработки команды, когда танк игрока не найден в пуле.
        """
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
                players={"player1": {"tank_id": "tank123"}}
            )
            self.mock_tank_pool.get_tank.return_value = None # Танк не найден
            message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
            mock_method = MagicMock(delivery_tag=128)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=128)

    def test_callback_json_decode_error(self):
        """
        Тест обработки сообщения, которое не является валидным JSON.
        """
        with patch.object(PlayerCommandConsumer, '_connect_and_declare', autospec=True):
            message_body = "Это не JSON строка" # Невалидный JSON
            mock_method = MagicMock(delivery_tag=129)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=129) # Сообщение подтверждается

# Декораторы на уровне класса для TestMatchmakingEventConsumer были удалены аналогично TestPlayerCommandConsumer.
# Используем `with patch(...)` в каждом методе.
class TestMatchmakingEventConsumer(unittest.TestCase):
    """
    Набор тестов для MatchmakingEventConsumer.
    Проверяет логику обработки событий матчмейкинга.
    """

    @classmethod
    def setUpClass(cls):
        cls.mock_pika_patcher = patch('pika.BlockingConnection', autospec=True)
        cls.mock_BlockingConnection = cls.mock_pika_patcher.start()

        cls.mock_core_patcher = patch('core.message_broker_clients.get_rabbitmq_channel', autospec=True)
        cls.mock_get_rabbitmq_channel = cls.mock_core_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_pika_patcher.stop()
        cls.mock_core_patcher.stop()

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает мок-объект для SessionManager и экземпляр MatchmakingEventConsumer.
        """
        self.mock_BlockingConnection.reset_mock()
        self.mock_get_rabbitmq_channel.reset_mock()
        
        self.mock_session_manager = MagicMock(spec=SessionManager)
        with patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True):
            self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.mock_channel = self.mock_get_rabbitmq_channel.return_value
        self.consumer.rabbitmq_channel = self.mock_channel

    def test_callback_new_match_created(self):
        """
        Тест обработки события 'new_match_created'.
        Проверяет, что вызывается метод создания сессии и сообщение подтверждается.
        """
        with patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True):
            mock_created_session = MagicMock() # Мок для созданной сессии
            mock_created_session.session_id = "new_session_1"
            self.mock_session_manager.create_session.return_value = mock_created_session # Настраиваем возврат мок-сессии
            
            message_body = json.dumps({
                "event_type": "new_match_created",
                "match_details": {"map_id": "map_desert", "max_players": 4} # Пример деталей матча
            })
            mock_method = MagicMock(delivery_tag=201)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_session_manager.create_session.assert_called_once() # Метод создания сессии должен быть вызван
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=201) # Сообщение подтверждается

    def test_callback_unknown_event_type(self):
        """
        Тест обработки события с неизвестным типом.
        Проверяет, что метод создания сессии не вызывается и сообщение подтверждается.
        """
        with patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True):
            message_body = json.dumps({"event_type": "match_update", "details": {}}) # Неизвестный тип события
            mock_method = MagicMock(delivery_tag=202)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_session_manager.create_session.assert_not_called() # create_session не должен вызываться
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=202)

    def test_callback_json_decode_error_matchmaking(self):
        """
        Тест обработки сообщения, не являющегося валидным JSON, для MatchmakingEventConsumer.
        """
        with patch.object(MatchmakingEventConsumer, '_connect_and_declare', autospec=True):
            message_body = "определенно не json" # Невалидный JSON
            mock_method = MagicMock(delivery_tag=203)
            
            self.consumer._callback(self.mock_channel, mock_method, None, message_body.encode('utf-8'))
            
            self.mock_channel.basic_ack.assert_called_once_with(delivery_tag=203) # Сообщение подтверждается

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()