# game_server/command_consumer.py
import json
import logging
import time
import os

import pika
from pika.exceptions import AMQPConnectionError

from core.message_broker_clients import ( # Grouped imports for clarity
    get_rabbitmq_channel, 
    RABBITMQ_QUEUE_PLAYER_COMMANDS,
    RABBITMQ_QUEUE_MATCHMAKING_EVENTS, # Added import for the new queue
    KAFKA_DEFAULT_TOPIC_GAME_EVENTS, 
    send_kafka_message
)
from game_server.session_manager import SessionManager # Assuming SessionManager is accessible
from game_server.tank_pool import TankPool # Assuming TankPool is accessible

logger = logging.getLogger(__name__)

class PlayerCommandConsumer:
    def __init__(self, session_manager: SessionManager, tank_pool: TankPool):
        self.session_manager = session_manager
        self.tank_pool = tank_pool
        self.rabbitmq_channel = None
        self.connection = None
        # Ensure environment variables are fetched with defaults if necessary
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
        self.player_commands_queue = RABBITMQ_QUEUE_PLAYER_COMMANDS

        self._connect_and_declare()

    def _connect_and_declare(self):
        logger.info(f"PlayerCommandConsumer attempting to connect to RabbitMQ at {self.rabbitmq_host}...")
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.rabbitmq_host,
                                           heartbeat=600, # Keep connection alive
                                           blocked_connection_timeout=300)) # Timeout for blocked connection
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.player_commands_queue, durable=True)
            self.rabbitmq_channel.basic_qos(prefetch_count=1) # Process one message at a time
            logger.info(f"Successfully connected to RabbitMQ and declared queue '{self.player_commands_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}. Retrying in 5 seconds...")
            time.sleep(5)
            self._connect_and_declare() # Retry connection
        except Exception as e:
            logger.error(f"An unexpected error occurred during RabbitMQ setup: {e}")
            # Depending on policy, might retry or raise

    def _callback(self, ch, method, properties, body):
        try:
            logger.info(f"Received command via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode())
            player_id = message_data.get("player_id")
            command = message_data.get("command")
            details = message_data.get("details", {})

            if not player_id or not command:
                logger.error("Missing player_id or command in message.")
                ch.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge to remove from queue
                return

            session = self.session_manager.get_session_by_player_id(player_id)
            if not session:
                logger.warning(f"Player {player_id} not found in any session. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            player_data = session.players.get(player_id)
            if not player_data:
                logger.warning(f"Player data for {player_id} not found in session {session.session_id}. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank_id = player_data.get('tank_id')
            if not tank_id:
                logger.warning(f"Tank ID not found for player {player_id} in session {session.session_id}. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank = self.tank_pool.get_tank(tank_id)
            if not tank:
                logger.warning(f"Tank {tank_id} for player {player_id} not found in pool. Command '{command}' ignored.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            logger.info(f"Processing command '{command}' for player {player_id}, tank {tank_id}.")

            if command == "shoot":
                tank.shoot() # This method already sends a Kafka message
                # Additional logic related to shoot command outcome can be added here
                logger.info(f"Tank {tank_id} executed shoot command for player {player_id}.")
            elif command == "move":
                # Assuming 'details' contains 'new_position'
                new_position = details.get("new_position")
                if new_position:
                    tank.move(tuple(new_position)) # This method already sends a Kafka message
                    logger.info(f"Tank {tank_id} executed move to {new_position} for player {player_id}.")
                else:
                    logger.warning(f"No new_position in 'move' command details for player {player_id}.")
            # Add more command handlers as needed
            # Example:
            # elif command == "use_ability":
            #    ability_id = details.get("ability_id")
            #    if ability_id:
            #        # tank.use_ability(ability_id) # Assuming such a method exists
            #        logger.info(f"Tank {tank_id} used ability {ability_id} for player {player_id}.")
            #        # Send Kafka message for ability use if not handled in tank method
            #        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
            #            "event_type": "ability_used", "tank_id": tank.tank_id, 
            #            "ability_id": ability_id, "player_id": player_id, "timestamp": time.time()
            #        })
            #    else:
            #        logger.warning(f"No ability_id in 'use_ability' command for player {player_id}.")
            else:
                logger.warning(f"Unknown command '{command}' received for player {player_id}.")

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Acknowledge malformed message
        except Exception as e:
            logger.exception(f"Unexpected error processing RabbitMQ message: {body.decode()}")
            # Requeue message if appropriate, or send to dead-letter queue
            # For simplicity, we'll ack, but in production, consider requeue or DLQ
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Example: send to DLQ if configured
            ch.basic_ack(delivery_tag=method.delivery_tag)


    def start_consuming(self):
        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.warning("RabbitMQ channel is not open. Attempting to reconnect...")
            self._connect_and_declare() # Attempt to reconnect
            if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed: # Check again
                logger.error("Failed to reconnect RabbitMQ channel. Consumer cannot start.")
                return

        logger.info(f"Starting to consume messages from '{self.player_commands_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback
            # auto_ack=False # Already default, ensuring manual acknowledgment
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Consumer stopped by KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"Consumer error: {e}. Attempting to restart consuming...")
            # Potentially add a delay and retry mechanism here
            self.stop_consuming() # Clean up current state
            time.sleep(5) # Wait before retrying
            self.start_consuming() # Retry

    def stop_consuming(self):
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("Stopping RabbitMQ consumer...")
            self.rabbitmq_channel.stop_consuming() # Stop consuming
            # self.rabbitmq_channel.close() # Closing channel here might be too soon if connection is shared
            logger.info("RabbitMQ consumer stopped.")
        if self.connection and self.connection.is_open:
            logger.info("Closing RabbitMQ connection...")
            self.connection.close()
            logger.info("RabbitMQ connection closed.")

# Example of how this might be run (e.g., in a separate thread or process)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Mock objects for SessionManager and TankPool for standalone testing
    class MockSessionManager:
        def get_session_by_player_id(self, player_id):
            if player_id == "player123":
                mock_session = type('MockSession', (), {})() # Create a simple mock object
                mock_session.session_id = "session789"
                mock_session.players = {"player123": {"tank_id": "tankABC"}}
                return mock_session
            return None

    class MockTank:
        def __init__(self, tank_id):
            self.tank_id = tank_id
        def shoot(self):
            logger.info(f"MockTank {self.tank_id} is shooting.")
            # Simulate Kafka message sending as in the actual Tank class
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
                "event_type": "tank_shot", "tank_id": self.tank_id, "timestamp": time.time()
            })
        def move(self, new_position):
            logger.info(f"MockTank {self.tank_id} is moving to {new_position}.")
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, { # Or KAFKA_DEFAULT_TOPIC_TANK_COORDINATES
                "event_type": "tank_moved", "tank_id": self.tank_id, 
                "position": new_position, "timestamp": time.time()
            })


    class MockTankPool:
        def get_tank(self, tank_id):
            if tank_id == "tankABC":
                return MockTank(tank_id)
            return None

    # Ensure KAFKA_BOOTSTRAP_SERVERS is set for the mock Kafka client to attempt connection
    # os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092' # Set if not already set externally
    # os.environ['RABBITMQ_HOST'] = 'localhost' # Set if not already set externally

    logger.info("Initializing mock components for PlayerCommandConsumer test...")
    session_manager_mock = MockSessionManager()
    tank_pool_mock = MockTankPool()

    consumer = PlayerCommandConsumer(session_manager=session_manager_mock, tank_pool=tank_pool_mock)
    try:
        logger.info("Starting PlayerCommandConsumer for testing...")
        consumer.start_consuming()
    except Exception as e:
        logger.error(f"Failed to start consumer for testing: {e}")
    finally:
        logger.info("Cleaning up PlayerCommandConsumer test.")
        consumer.stop_consuming()

# Added MatchmakingEventConsumer class below

class MatchmakingEventConsumer:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.rabbitmq_channel = None
        self.connection = None
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
        self.matchmaking_events_queue = RABBITMQ_QUEUE_MATCHMAKING_EVENTS

        self._connect_and_declare()

    def _connect_and_declare(self):
        logger.info(f"MatchmakingEventConsumer attempting to connect to RabbitMQ at {self.rabbitmq_host}...")
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.rabbitmq_host, heartbeat=600, blocked_connection_timeout=300)
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.matchmaking_events_queue, durable=True)
            self.rabbitmq_channel.basic_qos(prefetch_count=1)
            logger.info(f"MatchmakingEventConsumer successfully connected and declared queue '{self.matchmaking_events_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"MatchmakingEventConsumer failed to connect to RabbitMQ: {e}. Retrying in 5 seconds...")
            time.sleep(5)
            self._connect_and_declare()
        except Exception as e:
            logger.error(f"An unexpected error occurred during MatchmakingEventConsumer RabbitMQ setup: {e}")

    def _callback(self, ch, method, properties, body):
        try:
            logger.info(f"Received matchmaking event via RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode())
            
            event_type = message_data.get("event_type")
            match_details = message_data.get("match_details", {})

            if event_type == "new_match_created":
                # SessionManager.create_session() already sends a Kafka message.
                session = self.session_manager.create_session()
                # Current GameSession doesn't store map_id or detailed room_name from matchmaking.
                # This could be an enhancement for GameSession and SessionManager.
                logger.info(f"New game session {session.session_id} created from matchmaking event. Details: {match_details}")
                # If we need to link specific players or set up the room further, that logic would go here.
            else:
                logger.warning(f"Unknown event_type '{event_type}' in matchmaking message. Ignoring.")

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from matchmaking message: {body.decode()}. Error: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.exception(f"Unexpected error processing matchmaking message: {body.decode()}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Ack to prevent requeue loops on errors

    def start_consuming(self):
        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.warning("MatchmakingEventConsumer RabbitMQ channel is not open. Attempting to reconnect...")
            self._connect_and_declare()
            if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
                logger.error("MatchmakingEventConsumer failed to reconnect RabbitMQ channel. Consumer cannot start.")
                return

        logger.info(f"MatchmakingEventConsumer starting to consume messages from '{self.matchmaking_events_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.matchmaking_events_queue,
            on_message_callback=self._callback
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("MatchmakingEventConsumer stopped by KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer error: {e}. Attempting to restart consuming...")
            self.stop_consuming()
            time.sleep(5)
            self.start_consuming()

    def stop_consuming(self):
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("Stopping MatchmakingEventConsumer RabbitMQ consumer...")
            self.rabbitmq_channel.stop_consuming()
            logger.info("MatchmakingEventConsumer RabbitMQ consumer stopped.")
        if self.connection and self.connection.is_open:
            logger.info("Closing MatchmakingEventConsumer RabbitMQ connection...")
            self.connection.close()
            logger.info("MatchmakingEventConsumer RabbitMQ connection closed.")
