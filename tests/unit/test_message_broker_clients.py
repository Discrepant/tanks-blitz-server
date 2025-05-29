# tests/unit/test_message_broker_clients.py
# This file contains unit tests for the message broker clients,
# particularly for Kafka-related functions defined in core.message_broker_clients.
import unittest
from unittest.mock import MagicMock, patch, call 
import json 
import os 

import core.message_broker_clients 
from core.message_broker_clients import (
    get_kafka_producer,
    send_kafka_message,
    close_kafka_producer,
    delivery_report,
    KAFKA_BOOTSTRAP_SERVERS,
    KafkaException # Import KafkaException for simulating errors
)
# Import the actual Confluent Kafka Producer class with an alias for clarity in tests
from confluent_kafka import Producer as ConfluentKafkaProducer_actual

class TestKafkaClientConfluent(unittest.TestCase):
    """
    Test suite for Kafka client functions using the confluent-kafka library.
    """

    def setUp(self):
        """
        Set up before each test.
        Resets the global Kafka producer and saves/restores USE_MOCKS env var.
        """
        self.original_use_mocks = os.environ.get("USE_MOCKS")
        # Ensure _kafka_producer is reset before each test for isolation
        core.message_broker_clients._kafka_producer = None

    def tearDown(self):
        """
        Clean up after each test.
        Restores USE_MOCKS and ensures the global Kafka producer is cleaned up.
        """
        if self.original_use_mocks is not None:
            os.environ["USE_MOCKS"] = self.original_use_mocks
        elif "USE_MOCKS" in os.environ:
            del os.environ["USE_MOCKS"]
        
        # Attempt to clean up any producer instance that might have been created
        close_kafka_producer() 
        core.message_broker_clients._kafka_producer = None


    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual')
    def test_get_kafka_producer_real_when_use_mocks_false(self, MockActualProducer):
        """
        Test: get_kafka_producer creates a real Producer instance (mocked) when USE_MOCKS is "false".
        Checks that ConfluentKafkaProducer_actual is called with the correct configuration.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            core.message_broker_clients._kafka_producer = None # Ensure it's reset
            mock_producer_instance = MockActualProducer.return_value
            producer = get_kafka_producer()
            
            self.assertIsNotNone(producer, "Producer should not be None.")
            self.assertIs(producer, mock_producer_instance, "Returned producer is not the mock instance from MockActualProducer.")
            
            expected_config = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all',
                'retries': 3,
                'linger.ms': 10
            }
            MockActualProducer.assert_called_once_with(expected_config)
            self.assertFalse(getattr(producer, '_is_custom_kafka_mock', False), "Real producer mock should not be marked as custom mock.")


    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual') # This mock is just to prevent real instantiation if logic fails
    def test_get_kafka_producer_mock_when_use_mocks_true(self, MockUnusedActualProducer):
        """
        Test: get_kafka_producer creates a MagicMock with spec when USE_MOCKS is "true".
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            core.message_broker_clients._kafka_producer = None # Ensure it's reset
            producer = get_kafka_producer()
            
            self.assertIsNotNone(producer, "Producer should not be None.")
            self.assertIsInstance(producer, MagicMock, "Producer should be MagicMock when USE_MOCKS='true'.")
            self.assertEqual(producer._spec_class, ConfluentKafkaProducer_actual, "Mock producer should have ConfluentKafkaProducer_actual spec.")
            self.assertTrue(getattr(producer, '_is_custom_kafka_mock', False), "Producer should be marked as _is_custom_kafka_mock.")
            self.assertIs(producer, core.message_broker_clients._kafka_producer, "Returned producer should be the global mock producer.")
            MockUnusedActualProducer.assert_not_called() # The real constructor should not be called
            
            # Check that our custom mock setup for produce and flush was done on the spec'd mock
            self.assertTrue(isinstance(producer.produce, MagicMock))
            self.assertTrue(isinstance(producer.flush, MagicMock))

    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual')
    def test_get_kafka_producer_returns_existing_producer(self, MockActualProducer):
        """
        Test: get_kafka_producer returns the existing instance on subsequent calls for both modes.
        """
        # Scenario 1: USE_MOCKS = "false"
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            core.message_broker_clients._kafka_producer = None 
            first_producer_real = get_kafka_producer()
            second_producer_real = get_kafka_producer()
            self.assertIs(first_producer_real, second_producer_real, "Subsequent calls should return the same real producer instance.")
            MockActualProducer.assert_called_once() 
        
        # Scenario 2: USE_MOCKS = "true"
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            core.message_broker_clients._kafka_producer = None 
            MockActualProducer.reset_mock() # Reset from previous scenario
            
            first_producer_mock = get_kafka_producer()
            second_producer_mock = get_kafka_producer()
            self.assertIs(first_producer_mock, second_producer_mock, "Subsequent calls should return the same mock producer instance.")
            self.assertTrue(getattr(first_producer_mock, '_is_custom_kafka_mock', False))
            MockActualProducer.assert_not_called()


    @patch('core.message_broker_clients.delivery_report') 
    def test_send_kafka_message_success_with_mock_producer(self, mock_delivery_report_func):
        """
        Test successful Kafka message sending using the custom mock producer.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            core.message_broker_clients._kafka_producer = None
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
    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual') 
    def test_send_kafka_message_no_producer_after_init_failure(self, MockActualProducer, mock_logger):
        """
        Test: send_kafka_message handles correctly when real producer creation fails.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            MockActualProducer.side_effect = KafkaException("Simulated Failed to create producer")
            core.message_broker_clients._kafka_producer = None 
            
            result = send_kafka_message("test_topic_fail", {"key": "value"})
            
            self.assertFalse(result, "send_kafka_message should return False if producer creation failed.")
            MockActualProducer.assert_called_once() 
            self.assertIsNone(core.message_broker_clients._kafka_producer, "Global producer should remain None after initialization error.")
            mock_logger.warning.assert_any_call("Kafka producer is unavailable. Message to topic test_topic_fail not sent: {'key': 'value'}")


    def test_close_kafka_producer_calls_flush_on_custom_mock(self):
        """
        Test: close_kafka_producer calls flush on the custom mock producer (USE_MOCKS="true").
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}):
            core.message_broker_clients._kafka_producer = None
            producer = get_kafka_producer() 
            self.assertTrue(isinstance(producer.flush, MagicMock))

            close_kafka_producer()
            
            producer.flush.assert_called_once_with(timeout=10)
            self.assertIsNone(core.message_broker_clients._kafka_producer, "Global mock producer should be None after close.")

    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual')
    def test_close_kafka_producer_calls_flush_on_real_producer_mock(self, MockActualProducer):
        """
        Test: close_kafka_producer calls flush on a mocked real producer instance.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            core.message_broker_clients._kafka_producer = None
            # First, get a "real" producer (which is actually a mock via @patch)
            # This ensures _kafka_producer is set to an instance that is not our "_is_custom_kafka_mock"
            mock_producer_instance = MockActualProducer.return_value
            mock_producer_instance.flush.return_value = 0 # Ensure flush returns an int
            core.message_broker_clients._kafka_producer = mock_producer_instance # Directly set it for this test
            
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
            delivery_report(None, mock_msg) 
            mock_logger.debug.assert_called_once_with(
                "Message delivered to topic my_topic partition 0 offset 100"
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
            delivery_report(err_message, mock_msg) 
            mock_logger.error.assert_called_once_with(
                f"Message delivery failed to topic my_topic partition 1: {err_message}"
            )

if __name__ == '__main__':
    unittest.main()
