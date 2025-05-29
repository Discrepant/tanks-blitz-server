# core/message_broker_clients.py
# Этот модуль предоставляет клиенты для взаимодействия с брокерами сообщений Kafka и RabbitMQ.
# Он включает функции для получения продюсера Kafka, канала RabbitMQ, отправки сообщений
# и очистки соединений. Также поддерживает режим мокирования для тестов.

import json
import logging
import os
import pika # Библиотека для работы с RabbitMQ
# Use an alias for the actual confluent_kafka.Producer to avoid confusion
from confluent_kafka import Producer as ConfluentKafkaProducer_actual, KafkaException 
from unittest.mock import MagicMock # Используется для мокирования в тестах
from typing import Optional # For type hinting

logger = logging.getLogger(__name__)

# Конфигурация Kafka
# Адрес серверов Kafka, по умолчанию 'localhost:9092'. Берется из переменной окружения KAFKA_BOOTSTRAP_SERVERS.
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
# Топик по умолчанию для истории сессий игроков.
KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS = 'player_sessions_history'
# Топик по умолчанию для истории координат танков.
KAFKA_DEFAULT_TOPIC_TANK_COORDINATES = 'tank_coordinates_history'
# Топик по умолчанию для игровых событий.
KAFKA_DEFAULT_TOPIC_GAME_EVENTS = 'game_events'
# Пример: Топик для событий аутентификации.
KAFKA_DEFAULT_TOPIC_AUTH_EVENTS = 'auth_events'


# Конфигурация RabbitMQ
# Хост RabbitMQ, по умолчанию 'localhost'. Берется из переменной окружения RABBITMQ_HOST.
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
# Очередь по умолчанию для команд игроков.
RABBITMQ_QUEUE_PLAYER_COMMANDS = 'player_commands'
# Очередь по умолчанию для событий матчмейкинга (пример).
RABBITMQ_QUEUE_MATCHMAKING_EVENTS = 'matchmaking_events'

# Глобальные переменные для хранения инстансов продюсера Kafka и соединения/канала RabbitMQ.
# Это позволяет переиспользовать соединения и избежать их частого создания.
_kafka_producer: Optional[ConfluentKafkaProducer_actual] = None # Added type hint
_rabbitmq_connection = None
_rabbitmq_channel = None

def delivery_report(err, msg):
    """ 
    Callback-функция, вызываемая для каждого сообщения, отправленного в Kafka,
    чтобы указать результат доставки. Активируется вызовами poll() или flush().
    """
    if err is not None:
        logger.error(f"Message delivery failed to topic {msg.topic()} partition {msg.partition()}: {err}")
    else:
        logger.debug(f"Message delivered to topic {msg.topic()} partition {msg.partition()} offset {msg.offset()}")

def get_kafka_producer():
    """
    Возвращает глобальный инстанс продюсера Kafka.
    Если переменная окружения USE_MOCKS установлена в "true", возвращает мок-объект.
    При первом вызове (или если продюсер не был инициализирован) создает и настраивает
    продюсера Confluent Kafka.
    """
    global _kafka_producer
    if os.getenv("USE_MOCKS") == "true":
        # Если используется режим моков
        if not (isinstance(_kafka_producer, MagicMock) and \
                  getattr(_kafka_producer, '_is_custom_kafka_mock', False) is True and \
                  _kafka_producer._spec_class == ConfluentKafkaProducer_actual): # Use the actual class for spec check
            # If _kafka_producer is not our custom spec'd mock, create it.
            # Use the actual confluent_kafka.Producer for the spec
            _kafka_producer = MagicMock(spec=ConfluentKafkaProducer_actual, name="GlobalMockKafkaProducer_spec_actual")
            # Mock specific methods that are used
            _kafka_producer.produce = MagicMock(name="MockKafkaProducer.produce")
            # confluent_kafka.Producer.flush() returns an int (number of messages still in queue)
            _kafka_producer.flush = MagicMock(name="MockKafkaProducer.flush", return_value=0) 
            _kafka_producer._is_custom_kafka_mock = True # Mark it as our custom mock
            logger.info("Global _kafka_producer (MagicMock spec'd as ConfluentKafkaProducer_actual) initialized in MOCK mode.")
        return _kafka_producer

    if _kafka_producer is None:
        try:
            # Конфигурация для продюсера Confluent Kafka
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all', # Ждать подтверждения от всех реплик в ISR (in-sync replicas)
                'retries': 3,   # Количество попыток повторной отправки перед тем, как считать сообщение недоставленным
                'linger.ms': 10 # Ожидание до 10 мс для группировки сообщений в батчи
                # 'message.timeout.ms': 30000 # Optional: producer request timeout
            }
            _kafka_producer = ConfluentKafkaProducer_actual(conf) # Use the actual class for instantiation
            logger.info(f"Confluent Kafka producer initialized with configuration: {conf}")
        except KafkaException as e: # Catch common KafkaException from confluent-kafka
            logger.error(f"Failed to initialize Confluent Kafka producer: {e}")
            _kafka_producer = None # In case of error, producer remains None
    return _kafka_producer

def send_kafka_message(topic, message_dict):
    """
    Отправляет сообщение в указанный топик Kafka.

    Args:
        topic (str): Имя топика Kafka.
        message_dict (dict): Словарь с сообщением, который будет сериализован в JSON.

    Returns:
        bool: True, если сообщение было успешно передано на отправку (доставка асинхронна),
              False в случае ошибки.
    """
    producer = get_kafka_producer()
    if producer:
        try:
            json_str = json.dumps(message_dict) # Сериализуем словарь в JSON-строку
            value_bytes = json_str.encode('utf-8') # Кодируем строку в байты UTF-8
            
            # Асинхронная отправка сообщения. delivery_report будет вызван позже.
            producer.produce(topic, value=value_bytes, callback=delivery_report)
            
            # poll() для обслуживания callback-функций доставки (и других).
            # Небольшой неблокирующий poll часто достаточен после каждого produce.
            # Для приложений с высокой пропускной способностью может потребоваться выделенный поток для poll().
            producer.poll(0) 
            # logger.debug(f"Message handed over for sending to Kafka topic {topic}: {message_dict}") # Log before delivery report
            return True # Indicates message was handed over for sending (delivery is asynchronous)
        except KafkaException as e: # Kafka specific errors
            logger.error(f"Failed to produce message to Kafka topic {topic}: {e}")
            return False
        except BufferError as e: # confluent_kafka.Producer.produce can raise BufferError if producer queue is full
            logger.error(f"Kafka producer queue is full. Message to topic {topic} not sent: {message_dict}. Error: {e}")
            # Optionally, could call poll() here to try to free up space, then retry,
            # or handle as a failure.
            # producer.poll(1) # Poll for a short time to clear queue
            return False
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred while sending Kafka message to topic {topic}: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"Kafka producer is unavailable. Message to topic {topic} not sent: {message_dict}")
        return False

def get_rabbitmq_channel():
    """
    Возвращает глобальный инстанс канала RabbitMQ.
    Если переменная окружения USE_MOCKS установлена в "true", возвращает мок-объект.
    При первом вызове (или если соединение/канал закрыты) устанавливает соединение
    с RabbitMQ, открывает канал и объявляет необходимые очереди.
    """
    global _rabbitmq_connection, _rabbitmq_channel
    if os.getenv("USE_MOCKS") == "true":
        if not (isinstance(_rabbitmq_channel, MagicMock) and hasattr(_rabbitmq_channel, '_is_custom_rabbitmq_mock')):
            # Создаем моки для соединения и канала, если они еще не созданы
            _rabbitmq_connection = MagicMock(name="GlobalMockRabbitMQConnection")
            _rabbitmq_connection.is_closed = False # Имитируем открытое соединение
            
            _rabbitmq_channel = MagicMock(name="GlobalMockRabbitMQChannel")
            # Мокируем основные методы канала
            _rabbitmq_channel.queue_declare = MagicMock(name="MockRabbitMQChannel.queue_declare")
            _rabbitmq_channel.basic_qos = MagicMock(name="MockRabbitMQChannel.basic_qos")
            _rabbitmq_channel.basic_publish = MagicMock(name="MockRabbitMQChannel.basic_publish")
            _rabbitmq_channel.basic_consume = MagicMock(name="MockRabbitMQChannel.basic_consume")
            _rabbitmq_channel.start_consuming = MagicMock(name="MockRabbitMQChannel.start_consuming")
            _rabbitmq_channel.stop_consuming = MagicMock(name="MockRabbitMQChannel.stop_consuming")
            _rabbitmq_channel.close = MagicMock(name="MockRabbitMQChannel.close")
            _rabbitmq_channel.is_open = True # Имитируем открытый канал
            _rabbitmq_channel.is_closed = False 
            _rabbitmq_channel._is_custom_rabbitmq_mock = True # Помечаем как наш кастомный мок

            # Теперь, когда мок _rabbitmq_channel существует, устанавливаем его как возвращаемое значение для connection.channel()
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
            logger.info(f"Connection to RabbitMQ established ({RABBITMQ_HOST}), channel opened.")
            # Declare queues as durable (survive broker restart)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"RabbitMQ queues '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' and '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' declared.")

        # If channel is not open or is closed (can happen if connection remained but channel closed)
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
    Публикует сообщение в RabbitMQ.

    Args:
        exchange_name (str): Имя точки обмена (exchange). Для отправки напрямую в очередь используется ''.
        routing_key (str): Ключ маршрутизации (обычно имя очереди при отправке напрямую).
        body (dict): Словарь с сообщением, который будет сериализован в JSON.

    Returns:
        bool: True, если сообщение успешно опубликовано, False в случае ошибки.
    """
    channel = get_rabbitmq_channel()
    if channel:
        try:
            channel.basic_publish(
                exchange=exchange_name, # Имя точки обмена
                routing_key=routing_key, # Ключ маршрутизации (имя очереди)
                body=json.dumps(body).encode('utf-8'), # Тело сообщения (JSON -> bytes)
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Make message persistent (survives broker restart)
                )
            )
            logger.debug(f"Message published to RabbitMQ, exchange '{exchange_name}', routing_key '{routing_key}': {body}")
            return True
        except Exception as e: # Any error during publication
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
            global _rabbitmq_channel # Mark channel as invalid so it's recreated on next call
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
            logger.error(f"Error while closing RabbitMQ channel: {e}")
    if _rabbitmq_connection is not None and _rabbitmq_connection.is_open:
        try:
            _rabbitmq_connection.close()
            logger.info("Connection to RabbitMQ closed.")
        except Exception as e:
            logger.error(f"Error while closing RabbitMQ connection: {e}")
    _rabbitmq_channel = None
    _rabbitmq_connection = None

def close_kafka_producer():
    """
    Сбрасывает (flush) все сообщения из очереди продюсера Kafka и освобождает ресурсы.
    Продюсер Confluent Kafka не имеет явного метода close(), сброс и обнуление ссылки
    позволяют сборщику мусора освободить ресурсы.
    """
    global _kafka_producer
    if _kafka_producer is not None:
        # Проверяем, является ли _kafka_producer специальным моком, который не должен вызывать flush.
        # No longer skipping flush for custom mocks. If it's a mock, it should have a flush method.
        # If it's a real producer, it also has a flush method.
        # The confluent_kafka.Producer does not have a close() method.
        try:
            logger.info(f"Attempting to call flush() for producer: {_kafka_producer}")
            # confluent_kafka.Producer.flush() returns an int (number of messages still in queue)
            # It can raise KafkaException for delivery failures if proper error handling is not in callbacks.
            # Or it can timeout.
            if hasattr(_kafka_producer, 'flush') and callable(_kafka_producer.flush):
                remaining_messages = _kafka_producer.flush(timeout=10) # timeout in seconds
                if remaining_messages > 0:
                    logger.warning(f"{remaining_messages} Kafka messages still in queue after flush timeout for producer {_kafka_producer}.")
                else:
                    logger.info(f"All Kafka messages successfully flushed for producer {_kafka_producer}.")
            else:
                logger.warning(f"Producer {_kafka_producer} does not have a callable 'flush' method. Skipping flush.")

        except KafkaException as e: # Specific to confluent_kafka.Producer.flush()
            logger.error(f"Error flushing Confluent Kafka producer {_kafka_producer}: {e}")
        except Exception as e: # Other potential errors (e.g., if _kafka_producer is a mock that raises differently)
            logger.error(f"An unexpected error occurred while flushing Kafka producer {_kafka_producer}: {e}", exc_info=True)
        
        _kafka_producer = None 
        logger.info("Kafka producer instance has been set to None after flush attempt or error.")


def cleanup_message_brokers():
    """ Performs cleanup of all message broker connections. """
    logger.info("Cleaning up message broker connections...")
    close_kafka_producer()
    close_rabbitmq_connection()

# Example usage and test if module is run directly.
if __name__ == '__main__':
    # Basic logging setup for test run.
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
        logger.error("Confluent Kafka producer could not be initialized for test.")

    logger.info("--- RabbitMQ Channel Test ---")
    rmq_chan_instance = get_rabbitmq_channel()
    if rmq_chan_instance:
        logger.info(f"RabbitMQ channel obtained: {rmq_chan_instance}")
        if publish_rabbitmq_message(
            exchange_name='', # Empty string for default exchange (direct to queue)
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, # Queue name as routing key
            body={"command": "test_command", "payload": "RabbitMQ is working!"}
        ):
            logger.info("Test message published to RabbitMQ.")
        else:
            logger.error("Failed to publish test message to RabbitMQ.")
    else:
        logger.error("RabbitMQ channel could not be obtained for test.")
        
    cleanup_message_brokers() # Cleanup connections after tests
    logger.info("Test script finished.")
