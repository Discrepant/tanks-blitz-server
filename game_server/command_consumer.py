# game_server/command_consumer.py
# Этот модуль содержит классы для потребления сообщений из RabbitMQ:
# - PlayerCommandConsumer: обрабатывает команды игроков.
# - MatchmakingEventConsumer: обрабатывает события от системы матчмейкинга.
import json
import logging
import time
import os

import pika # Клиент для RabbitMQ
from pika.credentials import PlainCredentials # Импорт для учетных данных
from pika.exceptions import AMQPConnectionError # Исключение при ошибке соединения с RabbitMQ

# Импортируем необходимые компоненты из других модулей проекта
from core.message_broker_clients import ( # Группируем импорты для ясности
    get_rabbitmq_channel, # Функция для получения канала RabbitMQ (не используется напрямую здесь, но может быть полезна)
    RABBITMQ_QUEUE_PLAYER_COMMANDS, # Имя очереди для команд игроков
    RABBITMQ_QUEUE_MATCHMAKING_EVENTS, # Имя очереди для событий матчмейкинга
    KAFKA_DEFAULT_TOPIC_GAME_EVENTS, # Топик Kafka для игровых событий
    send_kafka_message # Функция для отправки сообщений в Kafka
)
# Предполагается, что SessionManager и TankPool доступны для импорта
from game_server.session_manager import SessionManager 
from game_server.tank_pool import TankPool 

logger = logging.getLogger(__name__)

class PlayerCommandConsumer:
    """
    Потребитель команд игрока из RabbitMQ.

    Этот класс отвечает за подключение к RabbitMQ, получение сообщений с командами
    игроков, их обработку (например, вызов методов танка) и подтверждение сообщений.
    """
    def __init__(self, session_manager: SessionManager, tank_pool: TankPool):
        """
        Инициализирует потребителя команд игрока.

        Args:
            session_manager (SessionManager): Менеджер игровых сессий.
            tank_pool (TankPool): Пул объектов танков.
        """
        self.session_manager = session_manager
        self.tank_pool = tank_pool
        self.rabbitmq_channel = None # Канал RabbitMQ
        self.connection = None # Соединение с RabbitMQ
        
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'rabbitmq') # Изменено значение по умолчанию на 'rabbitmq'
        self.rabbitmq_port = int(os.environ.get('RABBITMQ_PORT', 5672))
        self.rabbitmq_user = os.environ.get('RABBITMQ_DEFAULT_USER', 'user')
        self.rabbitmq_pass = os.environ.get('RABBITMQ_DEFAULT_PASS', 'password')
        self.rabbitmq_vhost = os.environ.get('RABBITMQ_DEFAULT_VHOST', '/')
        
        self.player_commands_queue = RABBITMQ_QUEUE_PLAYER_COMMANDS # Имя очереди команд

    def _connect_and_declare(self):
        logger.info(f"PlayerCommandConsumer: Попытка подключения к RabbitMQ по адресу {self.rabbitmq_host}:{self.rabbitmq_port} (vhost: {self.rabbitmq_vhost}, user: {self.rabbitmq_user})...") # PlayerCommandConsumer: Попытка подключения к RabbitMQ...
        try:
            credentials = PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_pass)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    virtual_host=self.rabbitmq_vhost,
                    credentials=credentials,
                    heartbeat=600, # Пульс (heartbeat)
                    blocked_connection_timeout=300 # Таймаут заблокированного соединения
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.player_commands_queue, durable=True) # Объявление устойчивой очереди
            self.rabbitmq_channel.basic_qos(prefetch_count=1) # Ограничение предварительной выборки одним сообщением
            logger.info(f"PlayerCommandConsumer: Успешное подключение к RabbitMQ и объявление очереди '{self.player_commands_queue}'.") # PlayerCommandConsumer: Успешное подключение к RabbitMQ и объявление очереди...
        except AMQPConnectionError as e:
            logger.error(f"PlayerCommandConsumer: Не удалось подключиться к RabbitMQ в _connect_and_declare: {e}") # PlayerCommandConsumer: Ошибка подключения к RabbitMQ в _connect_and_declare...
            self.connection = None 
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Произошла непредвиденная ошибка во время настройки RabbitMQ: {e}", exc_info=True) # PlayerCommandConsumer: Непредвиденная ошибка во время настройки RabbitMQ...
            self.connection = None
            self.rabbitmq_channel = None

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих сообщений из RabbitMQ.
        """
        try:
            logger.info(f"PlayerCommandConsumer: Получена команда через RabbitMQ: {body.decode()}") # PlayerCommandConsumer: Получена команда через RabbitMQ...
            message_data = json.loads(body.decode()) 
            player_id = message_data.get("player_id")
            command = message_data.get("command")
            details = message_data.get("details", {})

            if not player_id or not command:
                logger.error("PlayerCommandConsumer: В сообщении отсутствуют player_id или command.") # PlayerCommandConsumer: В сообщении отсутствуют player_id или command.
                ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждение обработки сообщения
                return

            session = self.session_manager.get_session_by_player_id(player_id)
            if not session:
                logger.warning(f"PlayerCommandConsumer: Игрок {player_id} не найден ни в одной сессии. Команда '{command}' проигнорирована.") # PlayerCommandConsumer: Игрок ... не найден... Команда ... проигнорирована.
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            player_data = session.players.get(player_id)
            if not player_data:
                logger.warning(f"PlayerCommandConsumer: Данные игрока {player_id} не найдены в сессии {session.session_id}. Команда '{command}' проигнорирована.") # PlayerCommandConsumer: Данные игрока ... не найдены... Команда ... проигнорирована.
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank_id = player_data.get('tank_id')
            if not tank_id:
                logger.warning(f"PlayerCommandConsumer: ID танка не найден для игрока {player_id} в сессии {session.session_id}. Команда '{command}' проигнорирована.") # PlayerCommandConsumer: ID танка не найден... Команда ... проигнорирована.
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank = self.tank_pool.get_tank(tank_id)
            if not tank:
                logger.warning(f"PlayerCommandConsumer: Танк {tank_id} для игрока {player_id} не найден в пуле. Команда '{command}' проигнорирована.") # PlayerCommandConsumer: Танк ... не найден... Команда ... проигнорирована.
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            logger.info(f"PlayerCommandConsumer: Обработка команды '{command}' для игрока {player_id}, танк {tank_id}.") # PlayerCommandConsumer: Обработка команды...

            if command == "shoot":
                tank.shoot() 
                logger.info(f"PlayerCommandConsumer: Танк {tank_id} выполнил команду 'shoot' для игрока {player_id}.") # PlayerCommandConsumer: Танк ... выполнил команду 'shoot'...
            elif command == "move":
                new_position = details.get("new_position")
                if new_position:
                    tank.move(tuple(new_position)) 
                    logger.info(f"PlayerCommandConsumer: Танк {tank_id} выполнил команду 'move' в {new_position} для игрока {player_id}.") # PlayerCommandConsumer: Танк ... выполнил команду 'move'...
                else:
                    logger.warning(f"PlayerCommandConsumer: Отсутствует new_position в деталях команды 'move' для игрока {player_id}.") # PlayerCommandConsumer: Отсутствует new_position...
            else:
                logger.warning(f"PlayerCommandConsumer: Получена неизвестная команда '{command}' для игрока {player_id}.") # PlayerCommandConsumer: Получена неизвестная команда...

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждение обработки сообщения

        except json.JSONDecodeError as e:
            logger.error(f"PlayerCommandConsumer: Не удалось декодировать JSON из сообщения: {body.decode()}. Ошибка: {e}") # PlayerCommandConsumer: Ошибка декодирования JSON...
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем, чтобы избежать повторной обработки поврежденного сообщения
        except Exception as e:
            logger.exception(f"PlayerCommandConsumer: Непредвиденная ошибка при обработке сообщения RabbitMQ: {body.decode()}") # PlayerCommandConsumer: Непредвиденная ошибка при обработке сообщения RabbitMQ...
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем, чтобы избежать цикла ошибок


    def start_consuming(self):
        self._connect_and_declare() # Подключение и объявление очереди

        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.error("PlayerCommandConsumer: Не удалось установить соединение с RabbitMQ. Потребитель не может запуститься.") # PlayerCommandConsumer: Ошибка установки соединения с RabbitMQ...
            return

        logger.info(f"PlayerCommandConsumer: Запуск потребления сообщений из '{self.player_commands_queue}'...") # PlayerCommandConsumer: Запуск потребления сообщений...
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback # Регистрация callback-функции
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("PlayerCommandConsumer: Потребитель остановлен через KeyboardInterrupt.") # PlayerCommandConsumer: Потребитель остановлен KeyboardInterrupt.
            self.stop_consuming()
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Ошибка потребителя: {e}. Попытка перезапуска потребления...", exc_info=True) # PlayerCommandConsumer: Ошибка потребителя... Попытка перезапуска...
            self.stop_consuming() 
            time.sleep(5) # Пауза перед перезапуском
            self.start_consuming() # Рекурсивный вызов для перезапуска

    def stop_consuming(self):
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("PlayerCommandConsumer: Остановка потребителя RabbitMQ...") # PlayerCommandConsumer: Остановка потребителя RabbitMQ...
            try:
                self.rabbitmq_channel.stop_consuming() 
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Ошибка во время остановки потребления: {e}", exc_info=True) # PlayerCommandConsumer: Ошибка при остановке потребления...
            logger.info("PlayerCommandConsumer: Потребитель RabbitMQ остановлен.") # PlayerCommandConsumer: Потребитель RabbitMQ остановлен.
        if self.connection and self.connection.is_open:
            logger.info("PlayerCommandConsumer: Закрытие соединения с RabbitMQ...") # PlayerCommandConsumer: Закрытие соединения с RabbitMQ...
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Ошибка при закрытии соединения: {e}", exc_info=True) # PlayerCommandConsumer: Ошибка при закрытии соединения...
            logger.info("PlayerCommandConsumer: Соединение с RabbitMQ закрыто.") # PlayerCommandConsumer: Соединение с RabbitMQ закрыто.

class MatchmakingEventConsumer:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.rabbitmq_channel = None
        self.connection = None

        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'rabbitmq') # Изменено значение по умолчанию на 'rabbitmq'
        self.rabbitmq_port = int(os.environ.get('RABBITMQ_PORT', 5672))
        self.rabbitmq_user = os.environ.get('RABBITMQ_DEFAULT_USER', 'user')
        self.rabbitmq_pass = os.environ.get('RABBITMQ_DEFAULT_PASS', 'password')
        self.rabbitmq_vhost = os.environ.get('RABBITMQ_DEFAULT_VHOST', '/')

        self.matchmaking_events_queue = RABBITMQ_QUEUE_MATCHMAKING_EVENTS

    def _connect_and_declare(self):
        logger.info(f"MatchmakingEventConsumer: Попытка подключения к RabbitMQ по адресу {self.rabbitmq_host}:{self.rabbitmq_port} (vhost: {self.rabbitmq_vhost}, user: {self.rabbitmq_user})...") # MatchmakingEventConsumer: Попытка подключения к RabbitMQ...
        try:
            credentials = PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_pass)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    virtual_host=self.rabbitmq_vhost,
                    credentials=credentials,
                    heartbeat=600, # Пульс (heartbeat)
                    blocked_connection_timeout=300 # Таймаут заблокированного соединения
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.matchmaking_events_queue, durable=True) # Объявление устойчивой очереди
            self.rabbitmq_channel.basic_qos(prefetch_count=1) # Ограничение предварительной выборки одним сообщением
            logger.info(f"MatchmakingEventConsumer: Успешное подключение и объявление очереди '{self.matchmaking_events_queue}'.") # MatchmakingEventConsumer: Успешное подключение и объявление очереди...
        except AMQPConnectionError as e:
            logger.error(f"MatchmakingEventConsumer: Не удалось подключиться к RabbitMQ в _connect_and_declare: {e}") # MatchmakingEventConsumer: Ошибка подключения к RabbitMQ...
            self.connection = None
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: Произошла непредвиденная ошибка во время настройки RabbitMQ: {e}", exc_info=True) # MatchmakingEventConsumer: Непредвиденная ошибка во время настройки RabbitMQ...
            self.connection = None
            self.rabbitmq_channel = None

    def _callback(self, ch, method, properties, body):
        try:
            logger.info(f"MatchmakingEventConsumer: Получено событие матчмейкинга через RabbitMQ: {body.decode()}") # MatchmakingEventConsumer: Получено событие матчмейкинга...
            message_data = json.loads(body.decode())
            
            event_type = message_data.get("event_type")
            match_details = message_data.get("match_details", {})

            if event_type == "new_match_created":
                session = self.session_manager.create_session() 
                logger.info(f"MatchmakingEventConsumer: Новая игровая сессия {session.session_id} создана из события матчмейкинга. Детали: {match_details}") # MatchmakingEventConsumer: Новая игровая сессия ... создана ...
            else:
                logger.warning(f"MatchmakingEventConsumer: Неизвестный event_type '{event_type}' в сообщении матчмейкинга. Игнорируется.") # MatchmakingEventConsumer: Неизвестный event_type ... Игнорируется.

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждение обработки сообщения

        except json.JSONDecodeError as e:
            logger.error(f"MatchmakingEventConsumer: Не удалось декодировать JSON из сообщения матчмейкинга: {body.decode()}. Ошибка: {e}") # MatchmakingEventConsumer: Ошибка декодирования JSON...
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем, чтобы избежать повторной обработки
        except Exception as e:
            logger.exception(f"MatchmakingEventConsumer: Непредвиденная ошибка при обработке сообщения матчмейкинга: {body.decode()}") # MatchmakingEventConsumer: Непредвиденная ошибка при обработке сообщения...
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем

    def start_consuming(self):
        self._connect_and_declare() # Подключение и объявление очереди

        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.error("MatchmakingEventConsumer: Не удалось установить соединение с RabbitMQ. Потребитель не может запуститься.") # MatchmakingEventConsumer: Ошибка установки соединения с RabbitMQ...
            return

        logger.info(f"MatchmakingEventConsumer: Запуск потребления сообщений из '{self.matchmaking_events_queue}'...") # MatchmakingEventConsumer: Запуск потребления сообщений...
        self.rabbitmq_channel.basic_consume(
            queue=self.matchmaking_events_queue,
            on_message_callback=self._callback # Регистрация callback-функции
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("MatchmakingEventConsumer: Потребитель остановлен через KeyboardInterrupt.") # MatchmakingEventConsumer: Потребитель остановлен KeyboardInterrupt.
            self.stop_consuming()
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: Ошибка потребителя: {e}. Попытка перезапуска потребления...", exc_info=True) # MatchmakingEventConsumer: Ошибка потребителя... Попытка перезапуска...
            self.stop_consuming()
            time.sleep(5) # Пауза перед перезапуском
            self.start_consuming() # Рекурсивный вызов для перезапуска

    def stop_consuming(self):
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("MatchmakingEventConsumer: Остановка потребителя RabbitMQ...") # MatchmakingEventConsumer: Остановка потребителя RabbitMQ...
            try:
                self.rabbitmq_channel.stop_consuming()
            except Exception as e:
                 logger.error(f"MatchmakingEventConsumer: Ошибка во время остановки потребления: {e}", exc_info=True) # MatchmakingEventConsumer: Ошибка при остановке потребления...
            logger.info("MatchmakingEventConsumer: Потребитель RabbitMQ остановлен.") # MatchmakingEventConsumer: Потребитель RabbitMQ остановлен.
        if self.connection and self.connection.is_open:
            logger.info("MatchmakingEventConsumer: Закрытие соединения с RabbitMQ...") # MatchmakingEventConsumer: Закрытие соединения с RabbitMQ...
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"MatchmakingEventConsumer: Ошибка при закрытии соединения: {e}", exc_info=True) # MatchmakingEventConsumer: Ошибка при закрытии соединения...
            logger.info("MatchmakingEventConsumer: Соединение с RabbitMQ закрыто.") # MatchmakingEventConsumer: Соединение с RabbitMQ закрыто.

# Example test execution block from original file (modified for clarity)
# Блок для примера тестового выполнения из оригинального файла (изменен для ясности)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s  - %(module)s - %(message)s')
    
    # Mock objects for standalone testing
    # Mock-объекты для автономного тестирования
    class MockSessionManager:
        def get_session_by_player_id(self, player_id):
            if player_id == "player123":
                mock_session = type('MockSession', (), {})()
                mock_session.session_id = "session789"
                mock_session.players = {"player123": {"tank_id": "tankABC"}}
                return mock_session
            return None
        def create_session(self): # Added for MatchmakingEventConsumer / Добавлено для MatchmakingEventConsumer
            mock_session = type('MockSession', (), {})()
            mock_session.session_id = "new_mock_session_" + str(time.time())
            logger.info(f"MockSessionManager: created session {mock_session.session_id}")
            return mock_session


    class MockTank:
        def __init__(self, tank_id):
            self.tank_id = tank_id
        def shoot(self):
            logger.info(f"MockTank {self.tank_id} is shooting.")
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
                "event_type": "tank_shot", "tank_id": self.tank_id, "timestamp": time.time()
            })
        def move(self, new_position):
            logger.info(f"MockTank {self.tank_id} is moving to {new_position}.")
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, { 
                "event_type": "tank_moved", "tank_id": self.tank_id, 
                "position": new_position, "timestamp": time.time()
            })

    class MockTankPool:
        def get_tank(self, tank_id):
            if tank_id == "tankABC":
                return MockTank(tank_id)
            return None

    # Ensure KAFKA_BOOTSTRAP_SERVERS is set if send_kafka_message is to be tested
    # Убедитесь, что KAFKA_BOOTSTRAP_SERVERS установлен, если send_kafka_message будет тестироваться
    # os.environ['KAFKA_BOOTSTRAP_SERVERS'] = os.environ.get('KAFKA_BOOTSTRAP_SERVERS','localhost:29092') 
    # Ensure RabbitMQ env vars are set if not running in docker-compose context for this test
    # Убедитесь, что переменные окружения RabbitMQ установлены, если запуск не в контексте docker-compose для этого теста
    # os.environ['RABBITMQ_HOST'] = os.environ.get('RABBITMQ_HOST','localhost')
    # os.environ['RABBITMQ_DEFAULT_USER'] = os.environ.get('RABBITMQ_DEFAULT_USER','user')
    # os.environ['RABBITMQ_DEFAULT_PASS'] = os.environ.get('RABBITMQ_DEFAULT_PASS','password')


    logger.info("Initializing mock components for Consumer tests...")
    session_manager_mock = MockSessionManager()
    tank_pool_mock = MockTankPool()

    player_consumer = PlayerCommandConsumer(session_manager_mock, tank_pool_mock)
    matchmaking_consumer = MatchmakingEventConsumer(session_manager_mock)
    
    logger.info("Starting consumers for testing (will run indefinitely if not interrupted)...")
    # In a real test, these would be run in threads and stopped.
    # В реальном тесте они бы запускались в потоках и останавливались.
    # For this __main__ block, you'd typically run one or the other, or handle KeyboardInterrupt.
    # Для этого блока __main__ обычно запускают одного или другого, или обрабатывают KeyboardInterrupt.
    # player_consumer.start_consuming() 
    # matchmaking_consumer.start_consuming()
    # For a simple test, one could publish a message and then stop.
    # Для простого теста можно было бы опубликовать сообщение, а затем остановиться.
    # This block is mostly for illustrative purposes or manual testing.
    # Этот блок в основном для иллюстративных целей или ручного тестирования.
    print("Run consumers manually or in a separate test script for automated testing.") # Запускайте потребителей вручную или в отдельном тестовом скрипте для автоматизированного тестирования.
