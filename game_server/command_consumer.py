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
        # Убеждаемся, что переменные окружения извлекаются с значениями по умолчанию при необходимости
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost') # Хост RabbitMQ
        self.player_commands_queue = RABBITMQ_QUEUE_PLAYER_COMMANDS # Имя очереди команд

        # self._connect_and_declare() # Удалено из __init__

    def _connect_and_declare(self):
        logger.info(f"PlayerCommandConsumer: Attempting to connect to RabbitMQ at {self.rabbitmq_host}...")
        try:
            credentials = PlainCredentials(username='user', password='password') # Используем значения из docker-compose.yml
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=5672, # Явно указываем порт
                    virtual_host='/', # Стандартный virtual host
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.player_commands_queue, durable=True)
            self.rabbitmq_channel.basic_qos(prefetch_count=1)
            logger.info(f"PlayerCommandConsumer: Successfully connected to RabbitMQ and declared queue '{self.player_commands_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"PlayerCommandConsumer: Failed to connect to RabbitMQ in _connect_and_declare: {e}")
            self.connection = None # Убедимся, что они None при ошибке
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: An unexpected error occurred during RabbitMQ setup: {e}", exc_info=True)
            self.connection = None
            self.rabbitmq_channel = None

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих сообщений из RabbitMQ.

        Декодирует сообщение, извлекает данные команды, находит соответствующий
        танк и вызывает его методы. Подтверждает сообщение после обработки.

        Args:
            ch: Канал RabbitMQ.
            method: Метаданные метода доставки.
            properties: Свойства сообщения.
            body (bytes): Тело сообщения (ожидается JSON).
        """
        try:
            logger.info(f"PlayerCommandConsumer: Received command via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode()) # Декодируем JSON
            player_id = message_data.get("player_id")
            command = message_data.get("command")
            details = message_data.get("details", {}) # Детали команды, по умолчанию пустой словарь

            if not player_id or not command:
                logger.error("PlayerCommandConsumer: Message is missing player_id or command.")
                ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем сообщение, чтобы удалить его из очереди
                return

            session = self.session_manager.get_session_by_player_id(player_id)
            if not session:
                logger.warning(f"PlayerCommandConsumer: Player {player_id} not found in any session. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            player_data = session.players.get(player_id)
            if not player_data:
                logger.warning(f"PlayerCommandConsumer: Player data for {player_id} not found in session {session.session_id}. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank_id = player_data.get('tank_id')
            if not tank_id:
                logger.warning(f"PlayerCommandConsumer: Tank ID not found for player {player_id} in session {session.session_id}. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank = self.tank_pool.get_tank(tank_id)
            if not tank:
                logger.warning(f"PlayerCommandConsumer: Tank {tank_id} for player {player_id} not found in pool. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            logger.info(f"PlayerCommandConsumer: Processing command '{command}' for player {player_id}, tank {tank_id}.")

            if command == "shoot":
                tank.shoot() # Этот метод уже отправляет сообщение в Kafka
                # Дополнительная логика, связанная с результатом выстрела, может быть добавлена здесь
                logger.info(f"PlayerCommandConsumer: Tank {tank_id} executed 'shoot' command for player {player_id}.")
            elif command == "move":
                # Предполагается, что 'details' содержит 'new_position'
                new_position = details.get("new_position")
                if new_position:
                    tank.move(tuple(new_position)) # Этот метод уже отправляет сообщение в Kafka
                    logger.info(f"PlayerCommandConsumer: Tank {tank_id} executed 'move' to {new_position} for player {player_id}.")
                else:
                    logger.warning(f"PlayerCommandConsumer: Missing new_position in 'move' command details for player {player_id}.")
            # Добавляйте обработчики других команд по мере необходимости
            # Пример:
            # elif command == "use_ability":
            #    ability_id = details.get("ability_id")
            #    if ability_id:
            #        # tank.use_ability(ability_id) # Предполагая, что такой метод существует
            #        logger.info(f"PlayerCommandConsumer: Tank {tank_id} used ability {ability_id} for player {player_id}.")
            #        # Отправка сообщения Kafka об использовании способности, если это не обрабатывается в методе танка
            #        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
            #            "event_type": "ability_used", "tank_id": tank.tank_id, 
            #            "ability_id": ability_id, "player_id": player_id, "timestamp": time.time()
            #        })
            #    else:
            #        logger.warning(f"PlayerCommandConsumer: Missing ability_id in 'use_ability' command for player {player_id}.")
            else:
                logger.warning(f"PlayerCommandConsumer: Received unknown command '{command}' for player {player_id}.")

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем успешную обработку

        except json.JSONDecodeError as e:
            logger.error(f"PlayerCommandConsumer: Failed to decode JSON from message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем некорректное сообщение, чтобы удалить его
        except Exception as e:
            logger.exception(f"PlayerCommandConsumer: Unexpected error while processing RabbitMQ message: {body.decode()}")
            # Повторная постановка сообщения в очередь (requeue) если это уместно, или отправка в DLQ (dead-letter queue).
            # Для простоты, мы подтверждаем сообщение, но в продакшене рассмотрите requeue или DLQ.
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Пример: отправить в DLQ, если настроено
            ch.basic_ack(delivery_tag=method.delivery_tag) # Пока просто подтверждаем


    def start_consuming(self):
        """
        Начинает потребление сообщений из очереди RabbitMQ.
        Включает механизм повторного подключения и перезапуска потребления в случае ошибок.
        """
        self._connect_and_declare() # Добавлен вызов в начало метода

        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.error("PlayerCommandConsumer: Failed to establish connection with RabbitMQ. Consumer cannot start.")
            return

        logger.info(f"PlayerCommandConsumer: Starting consumption of messages from '{self.player_commands_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback
            # auto_ack=False # Уже по умолчанию, обеспечивает ручное подтверждение
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("PlayerCommandConsumer: Consumer stopped via KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Consumer error: {e}. Attempting to restart consumption...", exc_info=True)
            # Потенциально можно добавить задержку и механизм повторных попыток здесь
            self.stop_consuming() # Очищаем текущее состояние
            time.sleep(5) # Ожидание перед повторной попыткой
            self.start_consuming() # Повторная попытка

    def stop_consuming(self):
        """
        Останавливает потребление сообщений и закрывает соединение с RabbitMQ.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("PlayerCommandConsumer: Stopping RabbitMQ consumer...")
            try:
                self.rabbitmq_channel.stop_consuming() # Останавливаем потребление
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while stopping consumption: {e}", exc_info=True)
            # Закрытие канала здесь может быть преждевременным, если соединение используется совместно.
            # Однако, если этот консьюмер управляет своим каналом эксклюзивно, то можно закрыть.
            # self.rabbitmq_channel.close() 
            logger.info("PlayerCommandConsumer: RabbitMQ consumer stopped.")
        if self.connection and self.connection.is_open:
            logger.info("PlayerCommandConsumer: Closing connection to RabbitMQ...")
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while closing connection: {e}", exc_info=True)
            logger.info("PlayerCommandConsumer: Connection to RabbitMQ closed.")

# Пример того, как это может быть запущено (например, в отдельном потоке или процессе)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Мок-объекты для SessionManager и TankPool для автономного тестирования
    class MockSessionManager:
        """Мок-класс для SessionManager."""
        def get_session_by_player_id(self, player_id):
            if player_id == "player123":
                mock_session = type('MockSession', (), {})() # Создаем простой мок-объект
                mock_session.session_id = "session789"
                mock_session.players = {"player123": {"tank_id": "tankABC"}}
                return mock_session
            return None

    class MockTank:
        """Мок-класс для Tank."""
        def __init__(self, tank_id):
            self.tank_id = tank_id
        def shoot(self):
            logger.info(f"MockTank {self.tank_id} is shooting.")
            # Имитация отправки сообщения Kafka, как в реальном классе Tank
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
                "event_type": "tank_shot", "tank_id": self.tank_id, "timestamp": time.time()
            })
        def move(self, new_position):
            logger.info(f"MockTank {self.tank_id} is moving to {new_position}.")
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, { # Или KAFKA_DEFAULT_TOPIC_TANK_COORDINATES
                "event_type": "tank_moved", "tank_id": self.tank_id, 
                "position": new_position, "timestamp": time.time()
            })


    class MockTankPool:
        """Мок-класс для TankPool."""
        def get_tank(self, tank_id):
            if tank_id == "tankABC":
                return MockTank(tank_id)
            return None

    # Убедитесь, что KAFKA_BOOTSTRAP_SERVERS установлена, чтобы мок-клиент Kafka попытался подключиться
    # os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092' # Установите, если не установлено извне
    # os.environ['RABBITMQ_HOST'] = 'localhost' # Установите, если не установлено извне

    logger.info("Initializing mock components for PlayerCommandConsumer test...")
    session_manager_mock = MockSessionManager()
    tank_pool_mock = MockTankPool()

    consumer = PlayerCommandConsumer(session_manager=session_manager_mock, tank_pool=tank_pool_mock)
    try:
        logger.info("Starting PlayerCommandConsumer for testing...")
        consumer.start_consuming()
    except Exception as e:
        logger.error(f"Failed to start consumer for testing: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up PlayerCommandConsumer test.")
        consumer.stop_consuming()

# Добавлен класс MatchmakingEventConsumer ниже

class MatchmakingEventConsumer:
    """
    Потребитель событий матчмейкинга из RabbitMQ.

    Отвечает за получение событий, таких как 'new_match_created', и
    взаимодействие с SessionManager для создания новых игровых сессий.
    """
    def __init__(self, session_manager: SessionManager):
        """
        Инициализирует потребителя событий матчмейкинга.

        Args:
            session_manager (SessionManager): Менеджер игровых сессий.
        """
        self.session_manager = session_manager
        self.rabbitmq_channel = None
        self.connection = None
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
        self.matchmaking_events_queue = RABBITMQ_QUEUE_MATCHMAKING_EVENTS

        # self._connect_and_declare() # Удалено из __init__

    def _connect_and_declare(self):
        logger.info(f"MatchmakingEventConsumer: Attempting to connect to RabbitMQ at {self.rabbitmq_host}...")
        try:
            credentials = PlainCredentials(username='user', password='password') # Используем значения из docker-compose.yml
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=5672, # Явно указываем порт
                    virtual_host='/', # Стандартный virtual host
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.matchmaking_events_queue, durable=True)
            self.rabbitmq_channel.basic_qos(prefetch_count=1)
            logger.info(f"MatchmakingEventConsumer: Successfully connected and declared queue '{self.matchmaking_events_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"MatchmakingEventConsumer: Failed to connect to RabbitMQ in _connect_and_declare: {e}")
            self.connection = None
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: An unexpected error occurred during RabbitMQ setup: {e}", exc_info=True)
            self.connection = None
            self.rabbitmq_channel = None

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих событий матчмейкинга.
        """
        try:
            logger.info(f"MatchmakingEventConsumer: Received matchmaking event via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode())
            
            event_type = message_data.get("event_type")
            match_details = message_data.get("match_details", {}) # Детали матча

            if event_type == "new_match_created":
                # Метод SessionManager.create_session() уже отправляет сообщение в Kafka.
                session = self.session_manager.create_session() # Создаем новую сессию
                # Текущий GameSession не хранит map_id или детальное имя комнаты из матчмейкинга.
                # Это может быть улучшением для GameSession и SessionManager.
                logger.info(f"MatchmakingEventConsumer: New game session {session.session_id} created from matchmaking event. Details: {match_details}")
                # Если необходимо связать конкретных игроков или дополнительно настроить комнату, эта логика будет здесь.
            else:
                logger.warning(f"MatchmakingEventConsumer: Unknown event_type '{event_type}' in matchmaking message. Ignoring.")

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем сообщение

        except json.JSONDecodeError as e:
            logger.error(f"MatchmakingEventConsumer: Failed to decode JSON from matchmaking message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.exception(f"MatchmakingEventConsumer: Unexpected error while processing matchmaking message: {body.decode()}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем, чтобы избежать циклов повторной обработки при ошибках

    def start_consuming(self):
        """
        Начинает потребление событий матчмейкинга.
        """
        self._connect_and_declare() # Добавлен вызов в начало метода

        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.error("MatchmakingEventConsumer: Failed to establish connection with RabbitMQ. Consumer cannot start.")
            return

        logger.info(f"MatchmakingEventConsumer: Starting consumption of messages from '{self.matchmaking_events_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.matchmaking_events_queue,
            on_message_callback=self._callback
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("MatchmakingEventConsumer: Consumer stopped via KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: Consumer error: {e}. Attempting to restart consumption...", exc_info=True)
            self.stop_consuming()
            time.sleep(5)
            self.start_consuming()

    def stop_consuming(self):
        """
        Останавливает потребление событий и закрывает соединение.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("MatchmakingEventConsumer: Stopping RabbitMQ consumer...")
            try:
                self.rabbitmq_channel.stop_consuming()
            except Exception as e:
                 logger.error(f"MatchmakingEventConsumer: Error while stopping consumption: {e}", exc_info=True)
            logger.info("MatchmakingEventConsumer: RabbitMQ consumer stopped.")
        if self.connection and self.connection.is_open:
            logger.info("MatchmakingEventConsumer: Closing connection to RabbitMQ...")
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"MatchmakingEventConsumer: Error while closing connection: {e}", exc_info=True)
            logger.info("MatchmakingEventConsumer: Connection to RabbitMQ closed.")
