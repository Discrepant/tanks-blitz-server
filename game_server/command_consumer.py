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
        
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'rabbitmq') # Changed default to 'rabbitmq'
        self.rabbitmq_port = int(os.environ.get('RABBITMQ_PORT', 5672))
        self.rabbitmq_user = os.environ.get('RABBITMQ_DEFAULT_USER', 'user')
        self.rabbitmq_pass = os.environ.get('RABBITMQ_DEFAULT_PASS', 'password')
        self.rabbitmq_vhost = os.environ.get('RABBITMQ_DEFAULT_VHOST', '/')
        
        self.player_commands_queue = RABBITMQ_QUEUE_PLAYER_COMMANDS # Имя очереди команд

    def _connect_and_declare(self):
        logger.info(f"PlayerCommandConsumer: Attempting to connect to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port} (vhost: {self.rabbitmq_vhost}, user: {self.rabbitmq_user})...")
        try:
            credentials = PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_pass)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    virtual_host=self.rabbitmq_vhost,
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
            self.connection = None 
            self.rabbitmq_channel = None
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: An unexpected error occurred during RabbitMQ setup: {e}", exc_info=True)
            self.connection = None
            self.rabbitmq_channel = None

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих сообщений из RabbitMQ.
        """
        try:
            logger.info(f"PlayerCommandConsumer: Received command via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode()) 
            player_id = message_data.get("player_id")
            command = message_data.get("command")
            details = message_data.get("details", {})

            if not player_id or not command:
                logger.error("PlayerCommandConsumer: Message is missing player_id or command.")
                ch.basic_ack(delivery_tag=method.delivery_tag) 
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
                tank.shoot() 
                logger.info(f"PlayerCommandConsumer: Tank {tank_id} executed 'shoot' command for player {player_id}.")
            elif command == "move":
                new_position = details.get("new_position")
                if new_position:
                    tank.move(tuple(new_position)) 
                    logger.info(f"PlayerCommandConsumer: Tank {tank_id} executed 'move' to {new_position} for player {player_id}.")
                else:
                    logger.warning(f"PlayerCommandConsumer: Missing new_position in 'move' command details for player {player_id}.")
            else:
                logger.warning(f"PlayerCommandConsumer: Received unknown command '{command}' for player {player_id}.")

            ch.basic_ack(delivery_tag=method.delivery_tag) 

        except json.JSONDecodeError as e:
            logger.error(f"PlayerCommandConsumer: Failed to decode JSON from message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag) 
        except Exception as e:
            logger.exception(f"PlayerCommandConsumer: Unexpected error while processing RabbitMQ message: {body.decode()}")
            ch.basic_ack(delivery_tag=method.delivery_tag)


    def start_consuming(self):
        self._connect_and_declare() 

        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.error("PlayerCommandConsumer: Failed to establish connection with RabbitMQ. Consumer cannot start.")
            return

        logger.info(f"PlayerCommandConsumer: Starting consumption of messages from '{self.player_commands_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("PlayerCommandConsumer: Consumer stopped via KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Consumer error: {e}. Attempting to restart consumption...", exc_info=True)
            self.stop_consuming() 
            time.sleep(5) 
            self.start_consuming() 

    def stop_consuming(self):
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("PlayerCommandConsumer: Stopping RabbitMQ consumer...")
            try:
                self.rabbitmq_channel.stop_consuming() 
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while stopping consumption: {e}", exc_info=True)
            logger.info("PlayerCommandConsumer: RabbitMQ consumer stopped.")
        if self.connection and self.connection.is_open:
            logger.info("PlayerCommandConsumer: Closing connection to RabbitMQ...")
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Error while closing connection: {e}", exc_info=True)
            logger.info("PlayerCommandConsumer: Connection to RabbitMQ closed.")

class MatchmakingEventConsumer:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.rabbitmq_channel = None
        self.connection = None

        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'rabbitmq') # Changed default to 'rabbitmq'
        self.rabbitmq_port = int(os.environ.get('RABBITMQ_PORT', 5672))
        self.rabbitmq_user = os.environ.get('RABBITMQ_DEFAULT_USER', 'user')
        self.rabbitmq_pass = os.environ.get('RABBITMQ_DEFAULT_PASS', 'password')
        self.rabbitmq_vhost = os.environ.get('RABBITMQ_DEFAULT_VHOST', '/')

        self.matchmaking_events_queue = RABBITMQ_QUEUE_MATCHMAKING_EVENTS

    def _connect_and_declare(self):
        logger.info(f"MatchmakingEventConsumer: Attempting to connect to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port} (vhost: {self.rabbitmq_vhost}, user: {self.rabbitmq_user})...")
        try:
            credentials = PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_pass)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    virtual_host=self.rabbitmq_vhost,
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
        try:
            logger.info(f"MatchmakingEventConsumer: Received matchmaking event via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode())
            
            event_type = message_data.get("event_type")
            match_details = message_data.get("match_details", {})

            if event_type == "new_match_created":
                session = self.session_manager.create_session() 
                logger.info(f"MatchmakingEventConsumer: New game session {session.session_id} created from matchmaking event. Details: {match_details}")
            else:
                logger.warning(f"MatchmakingEventConsumer: Unknown event_type '{event_type}' in matchmaking message. Ignoring.")

            ch.basic_ack(delivery_tag=method.delivery_tag) 

        except json.JSONDecodeError as e:
            logger.error(f"MatchmakingEventConsumer: Failed to decode JSON from matchmaking message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.exception(f"MatchmakingEventConsumer: Unexpected error while processing matchmaking message: {body.decode()}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        self._connect_and_declare() 

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

# Example test execution block from original file (modified for clarity)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s  - %(module)s - %(message)s')
    
    # Mock objects for standalone testing
    class MockSessionManager:
        def get_session_by_player_id(self, player_id):
            if player_id == "player123":
                mock_session = type('MockSession', (), {})()
                mock_session.session_id = "session789"
                mock_session.players = {"player123": {"tank_id": "tankABC"}}
                return mock_session
            return None
        def create_session(self): # Added for MatchmakingEventConsumer
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
    # os.environ['KAFKA_BOOTSTRAP_SERVERS'] = os.environ.get('KAFKA_BOOTSTRAP_SERVERS','localhost:29092') 
    # Ensure RabbitMQ env vars are set if not running in docker-compose context for this test
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
    # For this __main__ block, you'd typically run one or the other, or handle KeyboardInterrupt.
    # player_consumer.start_consuming() 
    # matchmaking_consumer.start_consuming()
    # For a simple test, one could publish a message and then stop.
    # This block is mostly for illustrative purposes or manual testing.
    print("Run consumers manually or in a separate test script for automated testing.")
