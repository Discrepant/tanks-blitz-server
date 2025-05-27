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
    _kafka_producer as global_kafka_producer
)


class TestKafkaClientConfluent(unittest.TestCase):

    def setUp(self):
        core.message_broker_clients._kafka_producer = None

    def tearDown(self):
        close_kafka_producer()
        core.message_broker_clients._kafka_producer = None

    @patch('core.message_broker_clients.Producer')
    def test_get_kafka_producer_creates_producer(self, MockProducer):
        mock_producer_instance = MockProducer.return_value
        mock_producer_instance.flush.return_value = 0  # Ensure flush returns int for tearDown
        # Assign to global so tearDown's close_kafka_producer finds this mock
        # core.message_broker_clients._kafka_producer = mock_producer_instance 
        # No, get_kafka_producer will assign it.

        producer = get_kafka_producer()  # This will set the global _kafka_producer
        self.assertIsNotNone(producer)
        self.assertIs(producer, mock_producer_instance)

        expected_config = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'acks': 'all',
            'retries': 3,
            'linger.ms': 10
        }
        MockProducer.assert_called_once_with(expected_config)
        # Ensure the global one is set for tearDown to use it with configured flush
        self.assertIs(core.message_broker_clients._kafka_producer, mock_producer_instance)

    @patch('core.message_broker_clients.Producer')
    def test_get_kafka_producer_returns_existing_producer(self, MockProducer):
        # First call creates producer
        first_mock_instance = MockProducer.return_value
        first_mock_instance.flush.return_value = 0  # Setup for first instance

        producer1 = get_kafka_producer()  # This sets global _kafka_producer to first_mock_instance
        self.assertIs(producer1, first_mock_instance)
        MockProducer.assert_called_once()  # Producer constructor called once

        # Second call should return the same instance
        producer2 = get_kafka_producer()
        self.assertIs(producer2, first_mock_instance)  # Should be the same instance
        MockProducer.assert_called_once()  # Still called only once

    @patch('core.message_broker_clients.Producer')
    @patch('core.message_broker_clients.delivery_report')
    def test_send_kafka_message_success(self, mock_delivery_report_cb, MockProducer):
        mock_producer_instance = MockProducer.return_value
        mock_producer_instance.flush.return_value = 0  # Ensure flush returns int for tearDown
        core.message_broker_clients._kafka_producer = mock_producer_instance

        topic = "test_topic"
        message_dict = {"key": "value", "num": 123}
        expected_value_bytes = json.dumps(message_dict).encode('utf-8')

        result = send_kafka_message(topic, message_dict)
        self.assertTrue(result)

        mock_producer_instance.produce.assert_called_once_with(
            topic,
            value=expected_value_bytes,
            callback=core.message_broker_clients.delivery_report
        )
        self.assertEqual(mock_producer_instance.produce.call_args[1]['callback'],
                         core.message_broker_clients.delivery_report)
        mock_producer_instance.poll.assert_called_once_with(0)

    @patch('core.message_broker_clients.Producer')
    def test_send_kafka_message_no_producer_after_init_failure(self, MockProducer):
        MockProducer.side_effect = core.message_broker_clients.KafkaException("Producer creation failed")
        # No mock_producer_instance is successfully created and assigned to global, so no flush setting needed here
        core.message_broker_clients._kafka_producer = None

        result = send_kafka_message("test_topic_fail", {"key": "value"})

        self.assertFalse(result)
        MockProducer.assert_called_once()
        self.assertIsNone(core.message_broker_clients._kafka_producer)

    @patch('core.message_broker_clients.Producer')
    def test_close_kafka_producer_flushes(self, MockProducer):
        mock_producer_instance = MockProducer.return_value
        mock_producer_instance.flush.return_value = 0
        core.message_broker_clients._kafka_producer = mock_producer_instance

        close_kafka_producer()

        mock_producer_instance.flush.assert_called_once_with(timeout=10)
        self.assertIsNone(core.message_broker_clients._kafka_producer)

    def test_delivery_report_success_direct_call(self):
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100

        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(None, mock_msg)
            mock_logger.debug.assert_called_once_with(
                f"Message delivered to topic my_topic partition 0 offset 100"
            )

    def test_delivery_report_failure_direct_call(self):
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 1
        err_message = "Broker: Message timed out"

        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(err_message, mock_msg)
            mock_logger.error.assert_called_once_with(
                f"Message delivery failed for topic my_topic partition 1: {err_message}"
            )


if __name__ == '__main__':
    unittest.main()