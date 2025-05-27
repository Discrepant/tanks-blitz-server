import unittest
from unittest.mock import MagicMock, patch, call
import json
import os

# Import functions and classes to be tested
# Assuming core.message_broker_clients is in PYTHONPATH
# For robust testing, ensure PYTHONPATH is set correctly or adjust import path
import core.message_broker_clients
from core.message_broker_clients import (
    get_kafka_producer,
    send_kafka_message,
    close_kafka_producer,
    delivery_report, # Also testable if made accessible or tested via send_kafka_message mock
    KAFKA_BOOTSTRAP_SERVERS, # Used for config
    _kafka_producer as global_kafka_producer # For cleanup checks
)

# Mock Producer from confluent_kafka # Class-level patch removed
class TestKafkaClientConfluent(unittest.TestCase):

    def setUp(self):
        # Reset the global producer for each test to ensure isolation
        # Accessing module-level variable for reset.
        core.message_broker_clients._kafka_producer = None


    def tearDown(self):
        # Clean up the global producer after each test
        # Call the actual close_kafka_producer to ensure its logic is covered.
        if isinstance(core.message_broker_clients._kafka_producer, MagicMock):
            if hasattr(core.message_broker_clients._kafka_producer, 'flush') and \
               isinstance(core.message_broker_clients._kafka_producer.flush, MagicMock):
                core.message_broker_clients._kafka_producer.flush.return_value = 0
        close_kafka_producer()
        # Explicitly set to None again in case close_kafka_producer was mocked or failed.
        core.message_broker_clients._kafka_producer = None

    @patch('core.message_broker_clients.Producer')
    def test_get_kafka_producer_creates_producer(self, MockProducer):
        mock_producer_instance = MockProducer.return_value
        
        producer = get_kafka_producer()
        self.assertIsNotNone(producer)
        self.assertIs(producer, mock_producer_instance)
        
        expected_config = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'acks': 'all', 
            'retries': 3,   
            'linger.ms': 10 
        }
        MockProducer.assert_called_once_with(expected_config)

    @patch('core.message_broker_clients.Producer')
    def test_get_kafka_producer_returns_existing_producer(self, MockProducer):
        # First call creates producer
        first_producer = get_kafka_producer()
        # Second call should return the same instance
        second_producer = get_kafka_producer()
        
        self.assertIs(first_producer, second_producer)
        MockProducer.assert_called_once() # Producer should only be created once

    @patch('core.message_broker_clients.Producer') # Outer decorator, mock will be last
    @patch('core.message_broker_clients.delivery_report') # Inner decorator, mock will be first
    def test_send_kafka_message_success(self, mock_delivery_report_param, MockProducer):
        # mock_delivery_report_param is the one from @patch
        # MockProducer is from the method-level patch
        
        mock_producer_instance = MockProducer.return_value
        # Manually set the global producer to our mock instance for this test
        core.message_broker_clients._kafka_producer = mock_producer_instance
        
        topic = "test_topic"
        message_dict = {"key": "value", "num": 123}
        expected_value_bytes = json.dumps(message_dict).encode('utf-8')
        
        result = send_kafka_message(topic, message_dict)
        self.assertTrue(result) # send_kafka_message should return True on successful production start
        
        mock_producer_instance.produce.assert_called_once_with(
            topic,
            value=expected_value_bytes,
            callback=core.message_broker_clients.delivery_report # Assert it's the actual function from the module
        )
        mock_producer_instance.poll.assert_called_once_with(0)

    @patch('core.message_broker_clients.Producer')
    def test_send_kafka_message_no_producer_after_init_failure(self, MockProducer):
        # Simulate producer creation failure when get_kafka_producer is called
        MockProducer.side_effect = core.message_broker_clients.KafkaException("Producer creation failed")
        
        # Ensure _kafka_producer is None so get_kafka_producer (called inside send_kafka_message)
        # will attempt to create it.
        core.message_broker_clients._kafka_producer = None 
        
        # Call send_kafka_message. This will internally call get_kafka_producer,
        # which will attempt to create Producer (and fail).
        result = send_kafka_message("test_topic_fail", {"key": "value"})
        
        # Assert that send_kafka_message handled the failure correctly
        self.assertFalse(result) 
        
        # Assert that Producer was attempted to be created exactly once
        MockProducer.assert_called_once() 
        
        # Assert that the global producer remains None after the failure
        self.assertIsNone(core.message_broker_clients._kafka_producer)

    @patch('core.message_broker_clients.Producer')
    def test_close_kafka_producer_flushes(self, MockProducer):
        mock_producer_instance = MockProducer.return_value
        mock_producer_instance.flush.return_value = 0
        # Simulate that a producer was created and is active
        core.message_broker_clients._kafka_producer = mock_producer_instance
        
        close_kafka_producer()
        
        mock_producer_instance.flush.assert_called_once_with(timeout=10) 
        self.assertIsNone(core.message_broker_clients._kafka_producer)

    # These tests for delivery_report are direct unit tests for the callback function itself.
    def test_delivery_report_success_direct_call(self): # REMOVE MockProducer
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        
        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(None, mock_msg) # err is None for success
            mock_logger.debug.assert_called_once_with(
                f"Message delivered to topic my_topic partition 0 offset 100"
            )

    def test_delivery_report_failure_direct_call(self): # REMOVE MockProducer
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 1
        err_message = "Broker: Message timed out"
        
        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(err_message, mock_msg) # err is not None for failure
            mock_logger.error.assert_called_once_with(
                f"Message delivery failed for topic my_topic partition 1: {err_message}"
            )

if __name__ == '__main__':
    unittest.main()
