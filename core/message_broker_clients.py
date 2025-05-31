# core/message_broker_clients.py
# Этот модуль предоставляет клиенты для взаимодействия с брокерами сообщений Kafka и RabbitMQ.
# Он включает функции для получения продюсера Kafka, канала RabbitMQ, отправки сообщений
# и очистки соединений. Также поддерживает режим мокирования для тестов.

import json
import logging
import os
import pika # Библиотека для работы с RabbitMQ
from unittest.mock import MagicMock # Используется для мокирования в тестах

logger = logging.getLogger(__name__)

# Флаг для отслеживания, была ли импортирована фактическая библиотека confluent_kafka
_confluent_kafka_successfully_imported = False

try:
    from confluent_kafka import Producer as ConfluentKafkaProducer_real_class, KafkaException as KafkaException_real_class
    
    # Если импорт успешен, это фактические классы/исключения, используемые модулем.
    ConfluentKafkaProducer_actual = ConfluentKafkaProducer_real_class
    KafkaException = KafkaException_real_class
    _confluent_kafka_successfully_imported = True
    logger.info("Библиотека 'confluent_kafka' успешно импортирована.")

except ImportError as e:
    _confluent_kafka_successfully_imported = False 
    if os.getenv("USE_MOCKS") == "true":
        logger.warning(
            "Не удалось импортировать библиотеку 'confluent_kafka'. "
            "Поскольку USE_MOCKS установлено в 'true', компоненты клиента Kafka будут замокированы. "
            f"Исходная ошибка: {e}"
        )
        # Мокируем сам класс Producer
        ConfluentKafkaProducer_actual = MagicMock(name="MockedConfluentKafkaProducerClassImportFallback")
        
        _mock_producer_instance = MagicMock(name="MockedConfluentKafkaProducerInstanceImportFallback")
        _mock_producer_instance.flush.return_value = 0 
        _mock_producer_instance.poll.return_value = None 
        _mock_producer_instance.produce.return_value = None 
        ConfluentKafkaProducer_actual.return_value = _mock_producer_instance
        
        KafkaException = type('MockedKafkaExceptionImportFallback', (Exception,), {})
        logger.info("Замокированы 'confluent_kafka.Producer' и 'confluent_kafka.KafkaException'.")
    else:
        logger.critical(
            "КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать библиотеку 'confluent_kafka', а USE_MOCKS не установлено в 'true'. "
            "Функциональность Kafka будет недоступна. Пожалуйста, установите пакет 'confluent-kafka-python'."
        )
        raise ImportError(
            "Библиотека 'confluent_kafka' не установлена, а USE_MOCKS не установлено в 'true'. "
            "Невозможно продолжить без клиента Kafka или явного режима мокирования."
        ) from e

# Kafka Configuration
# Kafka server address, default 'localhost:9092'. Taken from KAFKA_BOOTSTRAP_SERVERS environment variable.
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
# Default topic for player session history.
KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS = 'player_sessions_history'
# Default topic for tank coordinates history.
KAFKA_DEFAULT_TOPIC_TANK_COORDINATES = 'tank_coordinates_history'
# Default topic for game events.
KAFKA_DEFAULT_TOPIC_GAME_EVENTS = 'game_events'
# Example: Topic for authentication events.
KAFKA_DEFAULT_TOPIC_AUTH_EVENTS = 'auth_events'


# RabbitMQ Configuration
# RabbitMQ host, default 'localhost'. Taken from RABBITMQ_HOST environment variable.
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
# Default queue for player commands.
RABBITMQ_QUEUE_PLAYER_COMMANDS = 'player_commands'
# Default queue for matchmaking events (example).
RABBITMQ_QUEUE_MATCHMAKING_EVENTS = 'matchmaking_events'

# Global variables to store instances of Kafka producer and RabbitMQ connection/channel.
# This allows reusing connections and avoiding frequent creation.
_kafka_producer = None
_rabbitmq_connection = None
_rabbitmq_channel = None

def delivery_report(err, msg):
    """ 
    Callback function invoked for each message sent to Kafka
    to indicate the delivery result. Triggered by poll() or flush() calls.
    """
    if err is not None:
        logger.error(f"Message delivery failed for topic {msg.topic()} partition {msg.partition()}: {err}")
    else:
        logger.debug(f"Message delivered to topic {msg.topic()} partition {msg.partition()} offset {msg.offset()}")

def get_kafka_producer():
    """
    Returns the global Kafka producer instance.
    If USE_MOCKS environment variable is "true", returns a mock object.
    On first call (or if producer was not initialized), creates and configures
    a Confluent Kafka producer.
    """
    global _kafka_producer
    if os.getenv("USE_MOCKS") == "true":
        # If using mock mode
        # Simplified check: if _kafka_producer is not our custom mock, create it.
        if _kafka_producer is None or not getattr(_kafka_producer, '_is_custom_kafka_mock', False):
            # Create a MagicMock without spec_set to freely assign attributes.
            _kafka_producer = MagicMock(name="GlobalMockKafkaProducer")
            # Explicitly define flush, produce, and poll methods on the mock object _kafka_producer.
            _kafka_producer.flush = MagicMock(return_value=0, name="MockedFlushMethod")
            _kafka_producer.produce = MagicMock(name="MockedProduceMethod")
            _kafka_producer.poll = MagicMock(return_value=0, name="MockedPollMethod")
            _kafka_producer._is_custom_kafka_mock = True # Mark as our custom mock
            logger.info("Global _kafka_producer initialized in MOCK mode (from get_kafka_producer) with explicit flush, produce, poll methods.")
        return _kafka_producer

    if _kafka_producer is None:
        try:
            # Configuration for Confluent Kafka producer
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all', # Wait for acknowledgment from all in-sync replicas (ISR)
                'retries': 3,   # Number of retry attempts before considering a message undelivered
                'linger.ms': 10 # Wait up to 10 ms to group messages into batches
                # 'message.timeout.ms': 30000 # Optional: timeout for producer request
            }
            _kafka_producer = ConfluentKafkaProducer_actual(conf) # Use the alias here too
            logger.info(f"Confluent Kafka producer initialized with config: {conf}")
        except KafkaException as e: # Catch general KafkaException from confluent-kafka
            logger.error(f"Failed to initialize Confluent Kafka producer: {e}")
            _kafka_producer = None # Producer remains None in case of error
    return _kafka_producer

def send_kafka_message(topic, message_dict):
    """
    Sends a message to the specified Kafka topic.

    Args:
        topic (str): Name of the Kafka topic.
        message_dict (dict): Dictionary with the message, which will be serialized to JSON.

    Returns:
        bool: True if the message was successfully passed for sending (delivery is asynchronous),
              False in case of an error.
    """
    producer = get_kafka_producer()
    if producer:
        try:
            json_str = json.dumps(message_dict) # Serialize dictionary to JSON string
            value_bytes = json_str.encode('utf-8') # Encode string to UTF-8 bytes
            
            # Asynchronous message sending. delivery_report will be called later.
            producer.produce(topic, value=value_bytes, callback=delivery_report)
            
            # poll() to serve delivery callbacks (and others).
            # A small non-blocking poll is often sufficient after each produce.
            # High-throughput applications might require a dedicated poll thread.
            producer.poll(0) 
            # logger.debug(f"Message passed for sending to Kafka topic {topic}: {message_dict}") # Log before delivery report
            return True # Indicates message was passed for sending (delivery is asynchronous)
        except KafkaException as e: # Kafka-specific errors
            logger.error(f"Failed to pass message for sending to Kafka topic {topic}: {e}")
            return False
        except BufferError as e: # confluent_kafka.Producer.produce can raise BufferError if producer queue is full
            logger.error(f"Kafka producer queue is full. Message to topic {topic} not sent: {message_dict}. Error: {e}")
            # Optionally, can call poll() here to try to free up space, then retry,
            # or handle as failure.
            # producer.poll(1) # Poll for a short time to clear queue
            return False
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred while sending Kafka message to topic {topic}: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"Kafka producer is unavailable. Message to topic {topic} not sent: {message_dict}")
        return False

def get_rabbitmq_channel():
    logger.info(f"get_rabbitmq_channel: USE_MOCKS environment variable is currently '{os.getenv('USE_MOCKS')}' (type: {type(os.getenv('USE_MOCKS'))})") 
    """
    Returns the global RabbitMQ channel instance.
    If USE_MOCKS environment variable is "true", returns a mock object.
    On first call (or if connection/channel is closed), establishes a connection
    to RabbitMQ, opens a channel, and declares necessary queues.
    """
    global _rabbitmq_connection, _rabbitmq_channel
    if os.getenv("USE_MOCKS") == "true":
        if not (isinstance(_rabbitmq_channel, MagicMock) and hasattr(_rabbitmq_channel, '_is_custom_rabbitmq_mock')):
            # Create mocks for connection and channel if not already created
            _rabbitmq_connection = MagicMock(name="GlobalMockRabbitMQConnection")
            _rabbitmq_connection.is_closed = False # Simulate open connection
            
            _rabbitmq_channel = MagicMock(name="GlobalMockRabbitMQChannel")
            # Mock main channel methods
            _rabbitmq_channel.queue_declare = MagicMock(name="MockRabbitMQChannel.queue_declare")
            _rabbitmq_channel.basic_qos = MagicMock(name="MockRabbitMQChannel.basic_qos")
            _rabbitmq_channel.basic_publish = MagicMock(name="MockRabbitMQChannel.basic_publish")
            _rabbitmq_channel.basic_consume = MagicMock(name="MockRabbitMQChannel.basic_consume")
            _rabbitmq_channel.start_consuming = MagicMock(name="MockRabbitMQChannel.start_consuming")
            _rabbitmq_channel.stop_consuming = MagicMock(name="MockRabbitMQChannel.stop_consuming")
            _rabbitmq_channel.close = MagicMock(name="MockRabbitMQChannel.close")
            _rabbitmq_channel.is_open = True # Simulate open channel
            _rabbitmq_channel.is_closed = False 
            _rabbitmq_channel._is_custom_rabbitmq_mock = True # Mark as our custom mock

            # Now that _rabbitmq_channel mock exists, set it as the return value for connection.channel()
            _rabbitmq_connection.channel.return_value = _rabbitmq_channel
            logger.info("Global _rabbitmq_channel and _rabbitmq_connection initialized in MOCK mode.")
        return _rabbitmq_channel

    try:
        # If connection is not established or is closed
        if _rabbitmq_connection is None or _rabbitmq_connection.is_closed:
            _rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST) # Connection parameters
            )
            _rabbitmq_channel = _rabbitmq_connection.channel() # Open channel
            logger.info(f"RabbitMQ connection established ({RABBITMQ_HOST}), channel opened.")
            # Declare queues as durable (survive broker restart)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"RabbitMQ queues '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' and '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' declared.")

        # If channel is not open or is closed (can happen if connection remained, but channel closed)
        if _rabbitmq_channel is None or _rabbitmq_channel.is_closed:
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info("RabbitMQ channel was reopened.")
            # Re-declare queues in case they weren't declared before or channel is new
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)

    except pika.exceptions.AMQPConnectionError as e: # RabbitMQ connection error
        logger.error(f"Failed to connect to RabbitMQ or declare queue: {e}")
        _rabbitmq_connection = None
        _rabbitmq_channel = None
    return _rabbitmq_channel

def publish_rabbitmq_message(exchange_name, routing_key, body):
    """
    Publishes a message to RabbitMQ.

    Args:
        exchange_name (str): Name of the exchange. Use '' for sending directly to queue.
        routing_key (str): Routing key (usually queue name when sending directly).
        body (dict): Dictionary with the message, which will be serialized to JSON.

    Returns:
        bool: True if message was successfully published, False in case of error.
    """
    channel = get_rabbitmq_channel()
    if channel:
        try:
            channel.basic_publish(
                exchange=exchange_name, # Exchange name
                routing_key=routing_key, # Routing key (queue name)
                body=json.dumps(body).encode('utf-8'), # Message body (JSON -> bytes)
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Make message persistent (survives broker restart)
                )
            )
            logger.debug(f"Message published to RabbitMQ, exchange '{exchange_name}', routing_key '{routing_key}': {body}")
            return True
        except Exception as e: # Any error during publishing
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
            global _rabbitmq_channel # Mark channel as invalid so it gets recreated on next call
            _rabbitmq_channel = None 
            return False
    else:
        logger.warning(f"RabbitMQ channel is unavailable. Message for exchange '{exchange_name}', routing_key '{routing_key}' not sent: {body}")
        return False

def close_rabbitmq_connection():
    """ Closes RabbitMQ channel and connection if they are open. """
    global _rabbitmq_connection, _rabbitmq_channel
    if _rabbitmq_channel is not None and _rabbitmq_channel.is_open:
        try:
            _rabbitmq_channel.close()
            logger.info("RabbitMQ channel closed.")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ channel: {e}")
    if _rabbitmq_connection is not None and _rabbitmq_connection.is_open:
        try:
            _rabbitmq_connection.close()
            logger.info("RabbitMQ connection closed.")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
    _rabbitmq_channel = None
    _rabbitmq_connection = None

def close_kafka_producer():
    """
    Flushes all messages from Kafka producer queue and releases resources.
    Confluent Kafka producer doesn't have an explicit close() method, flushing and
    nullifying the reference allows garbage collector to free resources.
    """
    global _kafka_producer
    if _kafka_producer is not None:
        # Check if _kafka_producer is a special mock that shouldn't call flush.
        # These are mocks created by get_kafka_producer() when USE_MOCKS="true",
        # or those explicitly set in tests as simple MagicMocks without intent to test flush.
        is_simple_placeholder_mock = isinstance(_kafka_producer, MagicMock) and \
                                     getattr(_kafka_producer, '_is_custom_kafka_mock', False) is True # Check for explicit True

        if is_simple_placeholder_mock:
            logger.info(f"Kafka mock producer '{_kafka_producer._extract_mock_name()}' (marked as _is_custom_kafka_mock) nullified without calling flush.")
            _kafka_producer = None
            return

        # For all other cases (real producer or mock of real producer from @patch)
        # try to call flush.
        try:
            # Wait for all messages in producer queue to be sent.
            # Timeout is the maximum time to wait for ALL messages to be sent,
            # not for each message individually.
            logger.info(f"Attempting to call flush() for producer: {_kafka_producer}") # Added for clarity
            remaining_messages = _kafka_producer.flush(timeout=10) # timeout in seconds
            if remaining_messages > 0:
                logger.warning(f"{remaining_messages} Kafka messages still in queue after flush timeout.")
            else:
                logger.info("All Kafka messages successfully flushed.")
        except KafkaException as e: # General Kafka error during flush
            logger.error(f"Error flushing Confluent Kafka producer: {e}")
        except Exception as e: # Any other unexpected error during flush
            logger.error(f"An unexpected error occurred while flushing Kafka producer: {e}", exc_info=True)
        
        _kafka_producer = None 
        logger.info("Kafka producer resources released (set to None) after flush attempt or error.")


def cleanup_message_brokers():
    """ Performs cleanup of all message broker connections. """
    logger.info("Cleaning up message broker connections...")
    close_kafka_producer()
    close_rabbitmq_connection()

# Example usage and test if module is run directly.
if __name__ == '__main__':
    # Setup basic logging for test run.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    logger.info("--- Confluent Kafka Producer Test ---")
    kafka_prod_instance = get_kafka_producer()
    if kafka_prod_instance:
        test_message = {"event_type": "test_event", "detail": "Confluent Kafka is working!"}
        if send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, test_message):
            logger.info(f"Test message sent to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}: {test_message}")
        else:
            logger.error(f"Failed to send test message to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}.")
        # In a real application, flush might be called less frequently or only on shutdown.
        # For this test, we call it to ensure delivery attempts for the test message.
        # kafka_prod_instance.flush(timeout=5) # Flushed in close_kafka_producer
    else:
        logger.error("Confluent Kafka producer cannot be initialized for test.")

    logger.info("--- RabbitMQ Channel Test ---")
    rmq_chan_instance = get_rabbitmq_channel()
    if rmq_chan_instance:
        logger.info(f"RabbitMQ channel obtained: {rmq_chan_instance}")
        if publish_rabbitmq_message(
            exchange_name='', # Empty string for default exchange (send directly to queue)
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, # Queue name as routing key
            body={"command": "test_command", "payload": "RabbitMQ is working!"}
        ):
            logger.info("Test message published to RabbitMQ.")
        else:
            logger.error("Failed to publish test message to RabbitMQ.")
    else:
        logger.error("RabbitMQ channel cannot be obtained for test.")
        
    cleanup_message_brokers() # Cleanup connections after tests
    logger.info("Test script finished.")
