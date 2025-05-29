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

        # self._connect_and_declare() # Removed from __init__

    def _connect_and_declare(self):
        user = 'user' # Default user, consider making this configurable if needed
        logger.info(f"PlayerCommandConsumer: Attempting to connect to RabbitMQ: host={self.rabbitmq_host}, port=5672, user='{user}'...")
        try:
            credentials = PlainCredentials(username=user, password='password') # Using values from docker-compose.yml
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=5672, # Explicitly specify port
                    virtual_host='/', # Standard virtual host
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            )
            logger.info(f"PlayerCommandConsumer: Successfully established connection to RabbitMQ at {self.rabbitmq_host}:5672.")
            self.rabbitmq_channel = self.connection.channel()
            logger.info(f"PlayerCommandConsumer: RabbitMQ channel opened successfully.")
            self.rabbitmq_channel.queue_declare(queue=self.player_commands_queue, durable=True)
            logger.info(f"PlayerCommandConsumer: Queue '{self.player_commands_queue}' declared successfully (durable=True).")
            self.rabbitmq_channel.basic_qos(prefetch_count=1)
            logger.info(f"PlayerCommandConsumer: QoS prefetch_count=1 set for channel.")
            logger.info(f"PlayerCommandConsumer: RabbitMQ setup completed for queue '{self.player_commands_queue}'.")
        except AMQPConnectionError as e:
            # AMQPConnectionError already includes details like host/port in its string representation
            logger.error(f"PlayerCommandConsumer: Failed to connect to RabbitMQ at {self.rabbitmq_host}:5672. Details: {e}. Check RabbitMQ server status and connection parameters.")
            self.connection = None # Ensure these are None on error
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: An unexpected error occurred during RabbitMQ setup for host {self.rabbitmq_host}. Error: {e}", exc_info=True)
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
            logger.error(f"PlayerCommandConsumer: Cannot start consuming. RabbitMQ channel not available or closed for host {self.rabbitmq_host}.")
            # Potentially add a retry mechanism for _connect_and_declare here if desired, before returning.
            return

        logger.info(f"PlayerCommandConsumer: Preparing to start consuming messages from queue '{self.player_commands_queue}' on host {self.rabbitmq_host}.")
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback
            # auto_ack=False # Already default, ensures manual acknowledgement
        )
        try:
            logger.info(f"PlayerCommandConsumer: Now starting blocking consumption loop for queue '{self.player_commands_queue}'.")
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("PlayerCommandConsumer: Consumption stopped via KeyboardInterrupt.")
            self.stop_consuming() # Ensure cleanup
        except Exception as e:
            # This specific error log for "Consumer error" is already quite clear.
            # Adding more context about the restart attempt.
            logger.error(f"PlayerCommandConsumer: An error occurred during message consumption from '{self.player_commands_queue}'. Error: {e}. Attempting to stop and restart consumption...", exc_info=True)
            self.stop_consuming() # Clean up current state
            logger.info(f"PlayerCommandConsumer: Waiting for 5 seconds before attempting to restart consumption for '{self.player_commands_queue}'.")
            time.sleep(5) # Wait before retrying
            logger.info(f"PlayerCommandConsumer: Attempting to restart consumption for '{self.player_commands_queue}'.")
            self.start_consuming() # Retry consumption

    def stop_consuming(self):
        """
        Stops message consumption and closes the RabbitMQ connection.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info(f"PlayerCommandConsumer: Attempting to stop consuming from queue '{self.player_commands_queue}' on channel {self.rabbitmq_channel}.")
            try:
                self.rabbitmq_channel.stop_consuming() # Stop consumption
                logger.info(f"PlayerCommandConsumer: Successfully stopped consuming from queue '{self.player_commands_queue}'.")
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while stopping consumption from queue '{self.player_commands_queue}': {e}", exc_info=True)
            # Closing the channel here might be premature if the connection is shared.
            # However, if this consumer exclusively manages its channel, it can be closed.
            # self.rabbitmq_channel.close() 
            # logger.info("PlayerCommandConsumer: RabbitMQ channel closed after stopping consumption.") # If channel is closed here
        else:
            logger.info(f"PlayerCommandConsumer: No active consumption to stop or channel already closed for queue '{self.player_commands_queue}'.")

        if self.connection and self.connection.is_open:
            logger.info(f"PlayerCommandConsumer: Attempting to close connection to RabbitMQ host {self.rabbitmq_host}.")
            try:
                self.connection.close()
                logger.info(f"PlayerCommandConsumer: Successfully closed connection to RabbitMQ host {self.rabbitmq_host}.")
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while closing RabbitMQ connection to host {self.rabbitmq_host}: {e}", exc_info=True)
        else:
            logger.info(f"PlayerCommandConsumer: No active RabbitMQ connection to close for host {self.rabbitmq_host} or connection already closed.")
        
        # Ensure these are reset after stopping
        self.rabbitmq_channel = None
        self.connection = None


# Example of how this might be run (e.g., in a separate thread or process)
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

        # self._connect_and_declare() # Removed from __init__

    def _connect_and_declare(self):
        user = 'user' # Default user
        logger.info(f"MatchmakingEventConsumer: Attempting to connect to RabbitMQ: host={self.rabbitmq_host}, port=5672, user='{user}'...")
        try:
            credentials = PlainCredentials(username=user, password='password') # Using values from docker-compose.yml
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=5672, # Explicitly specify port
                    virtual_host='/', # Standard virtual host
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            )
            logger.info(f"MatchmakingEventConsumer: Successfully established connection to RabbitMQ at {self.rabbitmq_host}:5672.")
            self.rabbitmq_channel = self.connection.channel()
            logger.info(f"MatchmakingEventConsumer: RabbitMQ channel opened successfully.")
            self.rabbitmq_channel.queue_declare(queue=self.matchmaking_events_queue, durable=True)
            logger.info(f"MatchmakingEventConsumer: Queue '{self.matchmaking_events_queue}' declared successfully (durable=True).")
            self.rabbitmq_channel.basic_qos(prefetch_count=1)
            logger.info(f"MatchmakingEventConsumer: QoS prefetch_count=1 set for channel.")
            logger.info(f"MatchmakingEventConsumer: RabbitMQ setup completed for queue '{self.matchmaking_events_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"MatchmakingEventConsumer: Failed to connect to RabbitMQ at {self.rabbitmq_host}:5672. Details: {e}. Check RabbitMQ server status and connection parameters.")
            self.connection = None
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: An unexpected error occurred during RabbitMQ setup for host {self.rabbitmq_host}. Error: {e}", exc_info=True)
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
            logger.error(f"MatchmakingEventConsumer: Cannot start consuming. RabbitMQ channel not available or closed for host {self.rabbitmq_host}.")
            return

        logger.info(f"MatchmakingEventConsumer: Preparing to start consuming messages from queue '{self.matchmaking_events_queue}' on host {self.rabbitmq_host}.")
        self.rabbitmq_channel.basic_consume(
            queue=self.matchmaking_events_queue,
            on_message_callback=self._callback
        )
        try:
            logger.info(f"MatchmakingEventConsumer: Now starting blocking consumption loop for queue '{self.matchmaking_events_queue}'.")
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("MatchmakingEventConsumer: Consumption stopped via KeyboardInterrupt.")
            self.stop_consuming() # Ensure cleanup
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: An error occurred during message consumption from '{self.matchmaking_events_queue}'. Error: {e}. Attempting to stop and restart consumption...", exc_info=True)
            self.stop_consuming() # Clean up current state
            logger.info(f"MatchmakingEventConsumer: Waiting for 5 seconds before attempting to restart consumption for '{self.matchmaking_events_queue}'.")
            time.sleep(5) # Wait before retrying
            logger.info(f"MatchmakingEventConsumer: Attempting to restart consumption for '{self.matchmaking_events_queue}'.")
            self.start_consuming() # Retry consumption

    def stop_consuming(self):
        """
        Stops event consumption and closes the connection.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info(f"MatchmakingEventConsumer: Attempting to stop consuming from queue '{self.matchmaking_events_queue}' on channel {self.rabbitmq_channel}.")
            try:
                self.rabbitmq_channel.stop_consuming()
                logger.info(f"MatchmakingEventConsumer: Successfully stopped consuming from queue '{self.matchmaking_events_queue}'.")
            except Exception as e:
                 logger.error(f"MatchmakingEventConsumer: Error while stopping consumption from queue '{self.matchmaking_events_queue}': {e}", exc_info=True)
            logger.info("MatchmakingEventConsumer: RabbitMQ consumer stopped.") # This log seems redundant if the one above is successful. Keeping for now.
        else:
            logger.info(f"MatchmakingEventConsumer: No active consumption to stop or channel already closed for queue '{self.matchmaking_events_queue}'.")

        if self.connection and self.connection.is_open:
            logger.info(f"MatchmakingEventConsumer: Attempting to close connection to RabbitMQ host {self.rabbitmq_host}.")
            try:
                self.connection.close()
                logger.info(f"MatchmakingEventConsumer: Successfully closed connection to RabbitMQ host {self.rabbitmq_host}.")
            except Exception as e:
                logger.error(f"MatchmakingEventConsumer: Error while closing RabbitMQ connection to host {self.rabbitmq_host}: {e}", exc_info=True)
        else:
            logger.info(f"MatchmakingEventConsumer: No active RabbitMQ connection to close for host {self.rabbitmq_host} or connection already closed.")
            
        # Ensure these are reset after stopping
        self.rabbitmq_channel = None
        self.connection = None
