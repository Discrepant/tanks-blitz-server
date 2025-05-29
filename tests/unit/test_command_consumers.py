# tests/unit/test_command_consumers.py
# This file contains unit tests for RabbitMQ command and event consumers,
# namely PlayerCommandConsumer and MatchmakingEventConsumer.
import unittest
from unittest.mock import MagicMock, patch, call # Mocking tools
import json # For working with JSON messages
import pika # For AMQPConnectionError simulation
import time # For time.sleep in retry logic simulation

# Assuming project structure allows this import path.
# If modules are in the project root or PYTHONPATH is different, the path might change.
from game_server.command_consumer import PlayerCommandConsumer, MatchmakingEventConsumer
from game_server.session_manager import SessionManager
from game_server.tank_pool import TankPool
from game_server.tank import Tank

# Note on using @patch decorators:
# Order matters. If you mock multiple objects,
# they are passed to the test method in "bottom-up" or "inside-out" order.
# e.g.:
# @patch('A')
# @patch('B')
# def test_something(self, mock_B, mock_A): ...
#
# Class-level patching of 'pika.BlockingConnection' is used here for convenience.

@patch('pika.BlockingConnection', autospec=True)
class TestPlayerCommandConsumer(unittest.TestCase):
    """
    Test suite for PlayerCommandConsumer.
    Verifies the logic for processing various player commands received from RabbitMQ.
    """

    def setUp(self, MockPikaBlockingConnection_from_decorator): 
        """
        Set up before each test.
        Creates mock objects for dependencies (SessionManager, TankPool)
        and an instance of PlayerCommandConsumer with these mocks.
        Also mocks the RabbitMQ channel and connection.
        """
        self.MockPikaBlockingConnection = MockPikaBlockingConnection_from_decorator
        self.MockPikaBlockingConnection.reset_mock()

        self.mock_session_manager = MagicMock(spec=SessionManager)
        self.mock_tank_pool = MagicMock(spec=TankPool)
        
        self.mock_connection_instance = self.MockPikaBlockingConnection.return_value 
        self.mock_channel_instance = self.mock_connection_instance.channel.return_value
        self.mock_channel_instance.name = "MockChannelInstancePlayer" 

        # Configure basic channel methods
        self.mock_channel_instance.queue_declare = MagicMock(name="MockChannel.queue_declare")
        self.mock_channel_instance.basic_qos = MagicMock(name="MockChannel.basic_qos")
        self.mock_channel_instance.basic_ack = MagicMock(name="MockChannel.basic_ack")
        self.mock_channel_instance.basic_consume = MagicMock(name="MockChannel.basic_consume")
        self.mock_channel_instance.start_consuming = MagicMock(name="MockChannel.start_consuming")
        self.mock_channel_instance.stop_consuming = MagicMock(name="MockChannel.stop_consuming")
        self.mock_channel_instance.is_open = True 
        self.mock_channel_instance.close = MagicMock(name="MockChannel.close")

        self.mock_connection_instance.is_open = True
        self.mock_connection_instance.close = MagicMock(name="MockConnection.close")
        
        self.consumer = PlayerCommandConsumer(
            session_manager=self.mock_session_manager,
            tank_pool=self.mock_tank_pool
        )
        # For tests directly calling _callback, we manually assign the channel.
        # For tests of start_consuming, _connect_and_declare will use the patched mocks.
        self.consumer.rabbitmq_channel = self.mock_channel_instance
        self.consumer.connection = self.mock_connection_instance


    def test_callback_shoot_command_success(self): # Removed injected mock argument
        """
        Test successful processing of a 'shoot' command.
        Verifies session/tank lookup, tank's shoot method, and ack are called.
        """
        mock_tank_instance = MagicMock(spec=Tank) 
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}} 
        )
        self.mock_tank_pool.get_tank.return_value = mock_tank_instance
        
        message_body = json.dumps({
            "player_id": "player1",
            "command": "shoot",
            "details": {}
        })
        mock_method = MagicMock(delivery_tag=123) 
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.get_session_by_player_id.assert_called_once_with("player1")
        self.mock_tank_pool.get_tank.assert_called_once_with("tank123")
        mock_tank_instance.shoot.assert_called_once() 
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=123) 

    def test_callback_unknown_command(self): # Removed injected mock argument
        """
        Test processing of an unknown command.
        Verifies the unknown command is correctly acknowledged (ack).
        """
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = MagicMock(spec=Tank)
        message_body = json.dumps({"player_id": "player1", "command": "fly", "details": {}}) # Unknown command
        mock_method = MagicMock(delivery_tag=125)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=125)

    def test_callback_missing_player_id(self): # Removed injected mock argument
        """
        Test processing of a message without a player_id.
        Verifies the message is acknowledged.
        """
        message_body = json.dumps({"command": "shoot", "details": {}}) # Missing player_id
        mock_method = MagicMock(delivery_tag=126)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=126)

    def test_callback_player_not_in_session(self): # Removed injected mock argument
        """
        Test processing a command from a player not found in an active session.
        """
        self.mock_session_manager.get_session_by_player_id.return_value = None # Player not in session
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=127)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=127)

    def test_callback_tank_not_found(self): # Removed injected mock argument
        """
        Test processing a command when the player's tank is not found in the pool.
        """
        self.mock_session_manager.get_session_by_player_id.return_value = MagicMock(
            players={"player1": {"tank_id": "tank123"}}
        )
        self.mock_tank_pool.get_tank.return_value = None # Tank not found
        message_body = json.dumps({"player_id": "player1", "command": "shoot", "details": {}})
        mock_method = MagicMock(delivery_tag=128)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=128)

    def test_callback_json_decode_error(self): # Removed injected mock argument
        """
        Test processing of a message that is not valid JSON.
        """
        message_body = "This is not a JSON string" # Invalid JSON
        mock_method = MagicMock(delivery_tag=129)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=129)

    def test_start_consuming_flow_success(self): # Removed injected mock argument
        """Test the successful flow of start_consuming."""
        # _connect_and_declare is called by start_consuming
        self.consumer.start_consuming()

        self.MockPikaBlockingConnection.assert_called_once()
        self.mock_connection_instance.channel.assert_called_once()
        self.mock_channel_instance.queue_declare.assert_called_once_with(queue=self.consumer.player_commands_queue, durable=True)
        self.mock_channel_instance.basic_qos.assert_called_once_with(prefetch_count=1)
        self.mock_channel_instance.basic_consume.assert_called_once_with(
            queue=self.consumer.player_commands_queue,
            on_message_callback=self.consumer._callback
        )
        self.mock_channel_instance.start_consuming.assert_called_once()

    def test_start_consuming_connection_error_triggers_retry_logic(self): # Removed injected mock argument
        """Test start_consuming when _connect_and_declare fails with AMQPConnectionError."""
        
        # Make the first call to BlockingConnection fail, then succeed on retry
        call_count_blocking_conn_manager = {'count': 0}
        def side_effect_manager_pika(*args, **kwargs):
            call_count_blocking_conn_manager['count'] += 1
            if call_count_blocking_conn_manager['count'] == 1:
                raise pika.exceptions.AMQPConnectionError("Primary Test connection error")
            return self.mock_connection_instance # Return the already configured mock connection
        
        self.MockPikaBlockingConnection.side_effect = side_effect_manager_pika
        
        with patch.object(self.consumer, 'stop_consuming', wraps=self.consumer.stop_consuming) as mock_stop_consuming_spy, \
             patch('time.sleep') as mock_sleep:
            
            self.consumer.start_consuming()

        self.assertGreaterEqual(self.MockPikaBlockingConnection.call_count, 2, "Should attempt connection at least twice")
        mock_stop_consuming_spy.assert_called_once() 
        mock_sleep.assert_called_once_with(5)
        self.mock_channel_instance.basic_consume.assert_called_once() 
        self.mock_channel_instance.start_consuming.assert_called_once()


    def test_start_consuming_keyboard_interrupt(self): # Removed injected mock argument
        """Test start_consuming handling KeyboardInterrupt."""
        self.mock_channel_instance.start_consuming.side_effect = KeyboardInterrupt
        with patch.object(self.consumer, 'stop_consuming') as mock_stop_consuming:
            self.consumer.start_consuming() # This will call _connect_and_declare successfully
        mock_stop_consuming.assert_called_once() # stop_consuming should be called due to KeyboardInterrupt

    def test_start_consuming_generic_exception_triggers_retry(self): # Removed injected mock argument
        """Test start_consuming handling a generic Exception during consumption."""
        
        # Manager for start_consuming side effect
        call_count_start_consuming_manager = {'count': 0}
        def side_effect_manager_for_start_consuming(*args, **kwargs):
            call_count_start_consuming_manager['count'] += 1
            if call_count_start_consuming_manager['count'] == 1:
                 raise Exception("Simulated generic consumption error")
            pass 
        self.mock_channel_instance.start_consuming.side_effect = side_effect_manager_for_start_consuming

        # Manager for Pika connection side effect (to ensure reconnect works)
        call_count_pika_manager = {'count': 0}
        original_pika_side_effect = self.MockPikaBlockingConnection.side_effect 
        def side_effect_pika_ensure_reconnect(*args, **kwargs):
            nonlocal call_count_pika_manager
            call_count_pika_manager['count'] += 1
            return self.mock_connection_instance # Always return a working mock connection
        self.MockPikaBlockingConnection.side_effect = side_effect_pika_ensure_reconnect

        with patch.object(self.consumer, 'stop_consuming', wraps=self.consumer.stop_consuming) as mock_stop_consuming_spy, \
             patch('time.sleep') as mock_sleep:
            self.consumer.start_consuming()
        
        self.MockPikaBlockingConnection.side_effect = original_pika_side_effect

        self.assertEqual(self.mock_channel_instance.start_consuming.call_count, 2, "start_consuming should be attempted twice")
        mock_stop_consuming_spy.assert_called_once()
        mock_sleep.assert_called_once_with(5)


    def test_stop_consuming_flow(self): # Removed injected mock argument
        """Test the successful flow of stop_consuming."""
        self.consumer.rabbitmq_channel = self.mock_channel_instance 
        self.consumer.connection = self.mock_connection_instance
        self.mock_channel_instance.is_open = True
        self.mock_connection_instance.is_open = True

        self.consumer.stop_consuming()

        self.mock_channel_instance.stop_consuming.assert_called_once()
        self.mock_connection_instance.close.assert_called_once()
        self.assertIsNone(self.consumer.rabbitmq_channel)
        self.assertIsNone(self.consumer.connection)


@patch('pika.BlockingConnection', autospec=True)
class TestMatchmakingEventConsumer(unittest.TestCase):
    """
    Test suite for MatchmakingEventConsumer.
    Verifies logic for processing matchmaking events.
    """

    def setUp(self, MockPikaBlockingConnection_from_decorator_match): # Corrected signature
        """
        Set up before each test.
        Creates a mock object for SessionManager and an instance of MatchmakingEventConsumer.
        """
        self.MockPikaBlockingConnection = MockPikaBlockingConnection_from_decorator_match # Correct assignment
        self.MockPikaBlockingConnection.reset_mock()

        self.mock_session_manager = MagicMock(spec=SessionManager)
        
        self.mock_connection_instance = self.MockPikaBlockingConnection.return_value
        self.mock_channel_instance = self.mock_connection_instance.channel.return_value
        self.mock_channel_instance.name = "MockChannelInstanceMatchmaking"

        self.mock_channel_instance.queue_declare = MagicMock(name="MockChannel.queue_declare")
        self.mock_channel_instance.basic_qos = MagicMock(name="MockChannel.basic_qos")
        self.mock_channel_instance.basic_ack = MagicMock(name="MockChannel.basic_ack")
        self.mock_channel_instance.basic_consume = MagicMock(name="MockChannel.basic_consume")
        self.mock_channel_instance.start_consuming = MagicMock(name="MockChannel.start_consuming")
        self.mock_channel_instance.stop_consuming = MagicMock(name="MockChannel.stop_consuming")
        self.mock_channel_instance.is_open = True
        self.mock_channel_instance.close = MagicMock(name="MockChannel.close")
        
        self.mock_connection_instance.is_open = True
        self.mock_connection_instance.close = MagicMock(name="MockConnection.close")

        self.consumer = MatchmakingEventConsumer(session_manager=self.mock_session_manager)
        self.consumer.rabbitmq_channel = self.mock_channel_instance
        self.consumer.connection = self.mock_connection_instance


    def test_callback_new_match_created(self): # Removed injected mock argument
        """
        Test processing of 'new_match_created' event.
        Verifies session creation method is called and message is acknowledged.
        """
        mock_created_session = MagicMock() 
        mock_created_session.session_id = "new_session_1"
        self.mock_session_manager.create_session.return_value = mock_created_session 
        
        message_body = json.dumps({
            "event_type": "new_match_created",
            "match_details": {"map_id": "map_desert", "max_players": 4} 
        })
        mock_method = MagicMock(delivery_tag=201)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.create_session.assert_called_once() 
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=201) 

    def test_callback_unknown_event_type(self): # Removed injected mock argument
        """
        Test processing of an event with an unknown type.
        Verifies session creation is not called and the message is acknowledged.
        """
        message_body = json.dumps({"event_type": "match_update", "details": {}}) 
        mock_method = MagicMock(delivery_tag=202)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_session_manager.create_session.assert_not_called() 
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=202)

    def test_callback_json_decode_error_matchmaking(self): # Removed injected mock argument
        """
        Test processing of a message that is not valid JSON for MatchmakingEventConsumer.
        """
        message_body = "definitely not json" 
        mock_method = MagicMock(delivery_tag=203)
        
        self.consumer._callback(self.mock_channel_instance, mock_method, None, message_body.encode('utf-8'))
        
        self.mock_channel_instance.basic_ack.assert_called_once_with(delivery_tag=203)

    def test_start_consuming_flow_success(self): # Removed injected mock argument
        """Test the successful flow of start_consuming for matchmaking."""
        self.consumer.start_consuming()

        self.MockPikaBlockingConnection.assert_called_once()
        self.mock_connection_instance.channel.assert_called_once()
        self.mock_channel_instance.queue_declare.assert_called_once_with(queue=self.consumer.matchmaking_events_queue, durable=True)
        self.mock_channel_instance.basic_qos.assert_called_once_with(prefetch_count=1)
        self.mock_channel_instance.basic_consume.assert_called_once_with(
            queue=self.consumer.matchmaking_events_queue,
            on_message_callback=self.consumer._callback
        )
        self.mock_channel_instance.start_consuming.assert_called_once()

    def test_stop_consuming_flow(self): # Removed injected mock argument
        """Test the successful flow of stop_consuming for matchmaking."""
        self.consumer.rabbitmq_channel = self.mock_channel_instance 
        self.consumer.connection = self.mock_connection_instance
        self.mock_channel_instance.is_open = True
        self.mock_connection_instance.is_open = True
        
        self.consumer.stop_consuming()

        self.mock_channel_instance.stop_consuming.assert_called_once()
        self.mock_connection_instance.close.assert_called_once()
        self.assertIsNone(self.consumer.rabbitmq_channel)
        self.assertIsNone(self.consumer.connection)


if __name__ == '__main__':
    # Run tests if the file is executed directly.
    unittest.main()