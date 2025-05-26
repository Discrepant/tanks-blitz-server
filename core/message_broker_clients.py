# core/message_broker_clients.py
import json
import logging
import os
import pika
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS = 'player_sessions_history'
KAFKA_DEFAULT_TOPIC_TANK_COORDINATES = 'tank_coordinates_history'
KAFKA_DEFAULT_TOPIC_GAME_EVENTS = 'game_events'

# RabbitMQ Configuration
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_QUEUE_PLAYER_COMMANDS = 'player_commands'
RABBITMQ_QUEUE_MATCHMAKING_EVENTS = 'matchmaking_events' # Example queue for matchmaking

_kafka_producer = None
_rabbitmq_connection = None
_rabbitmq_channel = None

def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is None or _kafka_producer.bootstrap_connected() is False:
        try:
            _kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                retries=3, # Number of retries before failing
                # linger_ms=10, # Optional: wait up to 10ms to batch messages
                # request_timeout_ms=30000, # Optional: producer request timeout
            )
            logger.info(f"KafkaProducer initialized with servers: {KAFKA_BOOTSTRAP_SERVERS}")
        except KafkaError as e:
            logger.error(f"Failed to initialize KafkaProducer: {e}")
            _kafka_producer = None # Ensure it's None if initialization failed
            # Depending on application requirements, this might raise an exception
            # or the application should handle a None producer.
    return _kafka_producer

def send_kafka_message(topic, message):
    producer = get_kafka_producer()
    if producer:
        try:
            future = producer.send(topic, message)
            # Optional: block for synchronous sends or add callbacks
            # result = future.get(timeout=10) 
            # logger.debug(f"Message sent to Kafka topic {topic}: {message}, result: {result}")
            return future # Return future for async handling if needed
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka topic {topic}: {e}")
            return None
    else:
        logger.warning(f"Kafka producer not available. Message to topic {topic} not sent: {message}")
        return None

def get_rabbitmq_channel():
    global _rabbitmq_connection, _rabbitmq_channel
    try:
        if _rabbitmq_connection is None or _rabbitmq_connection.is_closed:
            _rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST)
            )
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info(f"RabbitMQ connection established to {RABBITMQ_HOST} and channel opened.")
            # Declare queues that are known to be needed by producers/consumers
            # This is idempotent, so safe to call on reconnects.
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True) # Make queue durable
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"RabbitMQ queues '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' and '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' declared.")

        if _rabbitmq_channel is None or _rabbitmq_channel.is_closed:
             # If only channel is closed, but connection is open
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info("RabbitMQ channel re-opened.")
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)

    except pika.exceptions.AMQPConnectionError as e:
        logger.error(f"Failed to connect to RabbitMQ or declare queue: {e}")
        _rabbitmq_connection = None
        _rabbitmq_channel = None
    return _rabbitmq_channel

def publish_rabbitmq_message(exchange_name, routing_key, body):
    channel = get_rabbitmq_channel()
    if channel:
        try:
            channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=json.dumps(body).encode('utf-8'),
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Make message persistent
                )
            )
            logger.debug(f"Message published to RabbitMQ exchange '{exchange_name}' with routing key '{routing_key}': {body}")
            return True
        except Exception as e: # More specific exceptions like AMQPChannelError can be caught
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
            # Attempt to re-establish channel for next time if error seems channel related
            global _rabbitmq_channel
            _rabbitmq_channel = None 
            return False
    else:
        logger.warning(f"RabbitMQ channel not available. Message to exchange '{exchange_name}', routing_key '{routing_key}' not sent: {body}")
        return False

def close_rabbitmq_connection():
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
    global _kafka_producer
    if _kafka_producer is not None:
        try:
            _kafka_producer.flush(timeout_ms=10000) # Wait for all messages to be sent
            _kafka_producer.close(timeout_ms=10000)
            logger.info("Kafka producer flushed and closed.")
        except KafkaError as e:
            logger.error(f"Error closing Kafka producer: {e}")
        _kafka_producer = None

# Optional: a cleanup function to be called on application shutdown
def cleanup_message_brokers():
    logger.info("Cleaning up message broker connections...")
    close_kafka_producer()
    close_rabbitmq_connection()

# Example of how to use (primarily for testing this module, actual use will be from other modules)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    # Kafka Test
    logger.info("--- Kafka Producer Test ---")
    kafka_prod = get_kafka_producer()
    if kafka_prod:
        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {"event_type": "test_event", "detail": "Kafka is working!"})
        # Forcing a flush and close here for the test, in real app this is on shutdown
        # kafka_prod.flush() 
        # kafka_prod.close() 
        # _kafka_producer = None # Reset for potential next get_kafka_producer call in same script run
    else:
        logger.error("Kafka producer could not be initialized for test.")

    # RabbitMQ Test
    logger.info("--- RabbitMQ Channel Test ---")
    rmq_chan = get_rabbitmq_channel()
    if rmq_chan:
        logger.info(f"RabbitMQ channel acquired: {rmq_chan}")
        # Test publish
        publish_rabbitmq_message(
            exchange_name='', # Default exchange
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, 
            body={"command": "test_command", "payload": "RabbitMQ is working!"}
        )
        # close_rabbitmq_connection() # In real app this is on shutdown
    else:
        logger.error("RabbitMQ channel could not be acquired for test.")
        
    cleanup_message_brokers()
