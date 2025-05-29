# tests/unit/test_message_broker_clients.py
# This file contains unit tests for the message broker clients,
# particularly for Kafka-related functions defined in core.message_broker_clients.
import unittest
from unittest.mock import MagicMock, patch, call # Mocking tools
import json # For working with JSON messages
import os # For working with environment variables

# Import functions and classes for testing.
# It's assumed that core.message_broker_clients is in PYTHONPATH.
# For reliable testing, ensure PYTHONPATH is set correctly,
# or adjust the import path.
import core.message_broker_clients # Import the entire module to access global variables
from core.message_broker_clients import (
    get_kafka_producer,         # Функция получения продюсера Kafka
    send_kafka_message,         # Функция отправки сообщения Kafka
    close_kafka_producer,       # Функция закрытия продюсера Kafka
    delivery_report,            # Callback-функция для отчета о доставке (также тестируема)
    KAFKA_BOOTSTRAP_SERVERS,    # Used for producer configuration
    _kafka_producer as global_kafka_producer, # Global producer variable for cleanup checks
    KafkaException              # Import KafkaException for simulating errors
)
from confluent_kafka import Producer as ConfluentKafkaProducer # For spec

# Mocking the Producer class from confluent_kafka.
# @patch decorator at class level was removed; using @patch in each method
# or context manager `with patch(...)` for more flexibility and clarity.
class TestKafkaClientConfluent(unittest.TestCase):
    """
    Test suite for Kafka client functions using the confluent-kafka library.
    """

    def setUp(self):
        """
        Set up before each test.
        Resets the global Kafka producer to ensure test isolation.
        Access to module-level variable for reset.
        """
        self.original_use_mocks = os.environ.get("USE_MOCKS")
        core.message_broker_clients._kafka_producer = None

    def tearDown(self):
        """
        Clean up after each test.
        Closes the global Kafka producer and explicitly sets it to None.
        Calls the real close_kafka_producer function to test its logic.
        """
        if self.original_use_mocks is not None:
            os.environ["USE_MOCKS"] = self.original_use_mocks
        elif "USE_MOCKS" in os.environ: # Check if it was set during the test
            del os.environ["USE_MOCKS"]

        # If the global producer was mocked, and it has a mock flush method,
        # ensure it returns 0 (no remaining messages) for proper completion.
        current_producer = core.message_broker_clients._kafka_producer
        if isinstance(current_producer, MagicMock) and \
           hasattr(current_producer, 'flush') and \
           isinstance(current_producer.flush, MagicMock):
            current_producer.flush.return_value = 0
        
        close_kafka_producer() # Call the real close function
        # Explicitly set to None in case close_kafka_producer was mocked or failed.
        core.message_broker_clients._kafka_producer = None

    @patch('core.message_broker_clients.Producer', spec=ConfluentKafkaProducer) 
    def test_get_kafka_producer_real_when_use_mocks_false(self, MockConfluentProducer):
        """
        Test: get_kafka_producer creates a real Producer instance when USE_MOCKS is "false".
        Checks that Producer is called with the correct configuration.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            mock_producer_instance = MockConfluentProducer.return_value
            producer = get_kafka_producer()
            
            self.assertIsNotNone(producer, "Producer should not be None.")
            self.assertIs(producer, mock_producer_instance, "Returned producer is not the mock instance.")
            
            expected_config = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all',
                'retries': 3,
                'linger.ms': 10
            }
            MockConfluentProducer.assert_called_once_with(expected_config)

    @patch('core.message_broker_clients.Producer', spec=ConfluentKafkaProducer)
    def test_get_kafka_producer_mock_when_use_mocks_true(self, MockConfluentProducer):
        """
        Test: get_kafka_producer creates a MagicMock with spec when USE_MOCKS is "true".
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            producer = get_kafka_producer()
            self.assertIsNotNone(producer, "Producer should not be None.")
            self.assertIsInstance(producer, MagicMock, "Producer should be MagicMock when USE_MOCKS='true'.")
            # Check that the spec was applied (the _spec_class is an internal MagicMock attribute)
            self.assertEqual(producer._spec_class, ConfluentKafkaProducer, "Mock producer should have ConfluentKafkaProducer spec.")
            self.assertTrue(getattr(producer, '_is_custom_kafka_mock', False), "Producer should be marked as _is_custom_kafka_mock.")
            self.assertIs(producer, core.message_broker_clients._kafka_producer, "Returned producer should be the global mock producer.")
            # The real confluent_kafka.Producer constructor should not be called
            MockConfluentProducer.assert_not_called() 
            # Check that our custom mock setup for produce and flush was done
            self.assertTrue(isinstance(producer.produce, MagicMock))
            self.assertTrue(isinstance(producer.flush, MagicMock))


    @patch('core.message_broker_clients.Producer', spec=ConfluentKafkaProducer)
    def test_get_kafka_producer_returns_existing_producer(self, MockConfluentProducer):
        """
        Test: get_kafka_producer returns the existing Producer instance on subsequent calls.
        Ensures the Producer constructor is called only once for real producers,
        and the same mock is returned when USE_MOCKS="true".
        """
        # Scenario 1: USE_MOCKS = "false"
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            core.message_broker_clients._kafka_producer = None # Ensure reset
            first_producer_real = get_kafka_producer()
            second_producer_real = get_kafka_producer()
            self.assertIs(first_producer_real, second_producer_real, "Subsequent calls should return the same real producer instance.")
            MockConfluentProducer.assert_called_once() # Constructor for real producer should be called only once.
        
        # Scenario 2: USE_MOCKS = "true"
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            core.message_broker_clients._kafka_producer = None # Ensure reset
            MockConfluentProducer.reset_mock() # Reset call count from previous scenario
            
            first_producer_mock = get_kafka_producer()
            second_producer_mock = get_kafka_producer()
            self.assertIs(first_producer_mock, second_producer_mock, "Subsequent calls should return the same mock producer instance.")
            self.assertTrue(getattr(first_producer_mock, '_is_custom_kafka_mock', False))
            # Real constructor should not be called when USE_MOCKS="true"
            MockConfluentProducer.assert_not_called()


    @patch('core.message_broker_clients.delivery_report') 
    def test_send_kafka_message_success_with_mock_producer(self, mock_delivery_report_func):
        """
        Test successful Kafka message sending using the custom mock producer.
        Ensures producer.produce and producer.poll are called correctly.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            # get_kafka_producer() will now return our spec'd MagicMock with mocked produce/flush
            mock_producer_instance = get_kafka_producer() 
            
            topic = "test_topic"
            message_dict = {"key": "value", "num": 123}
            expected_value_bytes = json.dumps(message_dict).encode('utf-8')
            
            result = send_kafka_message(topic, message_dict)
            self.assertTrue(result, "send_kafka_message should return True on successful send initiation.")
            
            mock_producer_instance.produce.assert_called_once_with(
                topic,
                value=expected_value_bytes,
                callback=core.message_broker_clients.delivery_report 
            )
            mock_producer_instance.poll.assert_called_once_with(0)

    @patch('core.message_broker_clients.logger')
    @patch('core.message_broker_clients.Producer', spec=ConfluentKafkaProducer)
    def test_send_kafka_message_no_producer_after_init_failure(self, MockConfluentProducer, mock_logger):
        """
        Test: send_kafka_message handles correctly when the producer cannot be created (real init failure).
        Ensures False is returned and a warning is logged.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            # Simulate failure during Producer creation
            MockConfluentProducer.side_effect = KafkaException("Failed to create producer")
            
            core.message_broker_clients._kafka_producer = None 
            
            result = send_kafka_message("test_topic_fail", {"key": "value"})
            
            self.assertFalse(result, "send_kafka_message should return False if producer creation failed.")
            MockConfluentProducer.assert_called_once() 
            self.assertIsNone(core.message_broker_clients._kafka_producer, "Global producer should remain None after initialization error.")
            # Check for the specific warning log
            mock_logger.warning.assert_any_call("Kafka producer is unavailable. Message to topic test_topic_fail not sent: {'key': 'value'}")


    def test_close_kafka_producer_calls_flush_on_custom_mock(self):
        """
        Test: close_kafka_producer calls flush on the custom mock producer (USE_MOCKS="true").
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            producer = get_kafka_producer() # This is our custom mock with a MagicMock 'flush'
            self.assertTrue(isinstance(producer.flush, MagicMock))

            close_kafka_producer()
            
            producer.flush.assert_called_once_with(timeout=10)
            self.assertIsNone(core.message_broker_clients._kafka_producer, "Global mock producer should be None after close.")

    @patch('core.message_broker_clients.Producer', spec=ConfluentKafkaProducer)
    def test_close_kafka_producer_calls_flush_on_real_producer_mock(self, MockConfluentProducer):
        """
        Test: close_kafka_producer calls flush on a mocked real producer instance.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            mock_producer_instance = MockConfluentProducer.return_value
            # Simulate that get_kafka_producer returned this instance
            core.message_broker_clients._kafka_producer = mock_producer_instance 
            
            close_kafka_producer()
            
            mock_producer_instance.flush.assert_called_once_with(timeout=10)
            self.assertIsNone(core.message_broker_clients._kafka_producer, "Global real producer mock should be None after close.")


    def test_delivery_report_success_direct_call(self): 
        """
        Test delivery_report callback on successful message delivery.
        """
        mock_msg = MagicMock() 
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        
        with patch('core.message_broker_clients.logger') as mock_logger: 
            delivery_report(None, mock_msg) # err is None on success
            mock_logger.debug.assert_called_once_with(
                "Message delivered to topic my_topic partition 0 offset 100" # Updated to English
            )

    def test_delivery_report_failure_direct_call(self):
        """
        Test delivery_report callback on failed message delivery.
        """
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 1
        err_message = "Broker: Message timed out" 
        
        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(err_message, mock_msg) # err is not None on failure
            mock_logger.error.assert_called_once_with(
                f"Message delivery failed to topic my_topic partition 1: {err_message}" # Updated to English
            )

if __name__ == '__main__':
    # Run tests if the file is executed directly.
    unittest.main()
