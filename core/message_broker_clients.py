# core/message_broker_clients.py
import json
import logging
import os
import pika
from confluent_kafka import Producer, KafkaException # KafkaError as ConfluentKafkaError (ConfluentKafkaError is not directly used, KafkaException is broader)

logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_DEFAULT_TOPIC_PLAYER_SESSIONS = 'player_sessions_history'
KAFKA_DEFAULT_TOPIC_TANK_COORDINATES = 'tank_coordinates_history'
KAFKA_DEFAULT_TOPIC_GAME_EVENTS = 'game_events'
# Example: Topic for authentication events
KAFKA_DEFAULT_TOPIC_AUTH_EVENTS = 'auth_events'


# RabbitMQ Configuration
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_QUEUE_PLAYER_COMMANDS = 'player_commands'
RABBITMQ_QUEUE_MATCHMAKING_EVENTS = 'matchmaking_events' # Example queue for matchmaking

_kafka_producer = None
_rabbitmq_connection = None
_rabbitmq_channel = None

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        logger.error(f"Message delivery failed for topic {msg.topic()} partition {msg.partition()}: {err}")
    else:
        logger.debug(f"Message delivered to topic {msg.topic()} partition {msg.partition()} offset {msg.offset()}")

def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is None:
        try:
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all', # Wait for all in-sync replicas to ack
                'retries': 3,   # Number of retries before failing
                'linger.ms': 10 # Wait up to 10ms to batch messages
                # 'message.timeout.ms': 30000 # Optional: producer request timeout
            }
            _kafka_producer = Producer(conf)
            logger.info(f"Confluent Kafka Producer initialized with config: {conf}")
        except KafkaException as e: # Catching generic KafkaException from confluent-kafka
            logger.error(f"Failed to initialize Confluent Kafka Producer: {e}")
            _kafka_producer = None
    return _kafka_producer

def send_kafka_message(topic, message_dict):
    producer = get_kafka_producer()
    if producer:
        try:
            json_str = json.dumps(message_dict)
            value_bytes = json_str.encode('utf-8')
            
            producer.produce(topic, value=value_bytes, callback=delivery_report)
            # Poll to serve delivery reports (and other callbacks)
            # A small non-blocking poll is often sufficient after each produce
            # For high-throughput applications, a dedicated polling thread might be better.
            producer.poll(0) 
            # logger.debug(f"Message produced to Kafka topic {topic}: {message_dict}") # Log before delivery report
            return True # Indicate message was produced (delivery is async)
        except KafkaException as e:
            logger.error(f"Failed to produce message to Kafka topic {topic}: {e}")
            return False
        except BufferError as e: # confluent_kafka.Producer.produce can raise BufferError if producer queue is full
            logger.error(f"Kafka producer queue full. Message to topic {topic} not sent: {message_dict}. Error: {e}")
            # Optionally, call poll() here to try to make space and then retry, or handle as a failure.
            # producer.poll(1) # Poll for a short time to clear queue
            return False
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred while sending Kafka message to topic {topic}: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"Kafka producer not available. Message to topic {topic} not sent: {message_dict}")
        return False

def get_rabbitmq_channel():
    global _rabbitmq_connection, _rabbitmq_channel
    try:
        if _rabbitmq_connection is None or _rabbitmq_connection.is_closed:
            _rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST)
            )
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info(f"RabbitMQ connection established to {RABBITMQ_HOST} and channel opened.")
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"RabbitMQ queues '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' and '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' declared.")

        if _rabbitmq_channel is None or _rabbitmq_channel.is_closed:
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
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                )
            )
            logger.debug(f"Message published to RabbitMQ exchange '{exchange_name}' with routing key '{routing_key}': {body}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
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
            # Wait for all messages in the Producer queue to be delivered.
            # The timeout is effectively the maximum time to wait for all messages
            # to be sent and acknowledged, not per message.
            remaining_messages = _kafka_producer.flush(timeout=10) # timeout in seconds
            if remaining_messages > 0:
                logger.warning(f"{remaining_messages} Kafka messages still in queue after flush timeout.")
            else:
                logger.info("All Kafka messages flushed successfully.")
        except KafkaException as e: # Catching generic KafkaException
            logger.error(f"Error flushing Confluent Kafka producer: {e}")
        except Exception as e: # Catch any other unexpected errors during flush
            logger.error(f"An unexpected error occurred during Kafka producer flush: {e}", exc_info=True)
        # confluent-kafka producer does not have an explicit close() method.
        # It's typically managed by Python's garbage collector.
        # Setting to None allows for re-initialization if needed.
        _kafka_producer = None 
        logger.info("Kafka producer resources released (set to None).")


def cleanup_message_brokers():
    logger.info("Cleaning up message broker connections...")
    close_kafka_producer()
    close_rabbitmq_connection()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    logger.info("--- Confluent Kafka Producer Test ---")
    kafka_prod_instance = get_kafka_producer()
    if kafka_prod_instance:
        test_message = {"event_type": "test_event", "detail": "Confluent Kafka is working!"}
        if send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, test_message):
            logger.info(f"Test message produced to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}: {test_message}")
        else:
            logger.error(f"Failed to produce test message to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}.")
        # In a real application, flush might be called less frequently or only at shutdown.
        # For this test, we call it to ensure delivery attempts for the test message.
        # kafka_prod_instance.flush(timeout=5) # Flushed in close_kafka_producer
    else:
        logger.error("Confluent Kafka producer could not be initialized for test.")

    logger.info("--- RabbitMQ Channel Test ---")
    rmq_chan_instance = get_rabbitmq_channel()
    if rmq_chan_instance:
        logger.info(f"RabbitMQ channel acquired: {rmq_chan_instance}")
        if publish_rabbitmq_message(
            exchange_name='', 
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, 
            body={"command": "test_command", "payload": "RabbitMQ is working!"}
        ):
            logger.info("Test message published to RabbitMQ.")
        else:
            logger.error("Failed to publish test message to RabbitMQ.")
    else:
        logger.error("RabbitMQ channel could not be acquired for test.")
        
    cleanup_message_brokers()
    logger.info("Test script finished.")
