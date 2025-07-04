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
    logger.info("Library 'confluent_kafka' imported successfully.")

except ImportError as e:
    _confluent_kafka_successfully_imported = False 
    if os.getenv("USE_MOCKS") == "true":
        logger.warning(
            "Failed to import library 'confluent_kafka'. "
            "Since USE_MOCKS is set to 'true', Kafka client components will be mocked. "
            f"Original error: {e}"
        )
        # Мокируем сам класс Producer
        ConfluentKafkaProducer_actual = MagicMock(name="MockedConfluentKafkaProducerClassImportFallback")
        
        _mock_producer_instance = MagicMock(name="MockedConfluentKafkaProducerInstanceImportFallback")
        _mock_producer_instance.flush.return_value = 0 
        _mock_producer_instance.poll.return_value = None 
        _mock_producer_instance.produce.return_value = None 
        ConfluentKafkaProducer_actual.return_value = _mock_producer_instance
        
        KafkaException = type('MockedKafkaExceptionImportFallback', (Exception,), {})
        logger.info("'confluent_kafka.Producer' and 'confluent_kafka.KafkaException' have been mocked.")
    else:
        logger.critical(
            "CRITICAL ERROR: Failed to import library 'confluent_kafka', and USE_MOCKS is not set to 'true'. "
            "Kafka functionality will be unavailable. Please install the 'confluent-kafka-python' package."
        )
        # Сообщение в исключении также должно быть переведено, если оно предназначено для оператора/разработчика, понимающего русский
        raise ImportError(
            "Library 'confluent_kafka' is not installed, and USE_MOCKS is not set to 'true'. "
            "Cannot continue without Kafka client or explicit mock mode."
        ) from e

# Конфигурация Kafka
# Адрес сервера Kafka, по умолчанию 'localhost:9092'. Берется из переменной окружения KAFKA_BOOTSTRAP_SERVERS.
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

# Глобальные переменные для хранения экземпляров продюсера Kafka и соединения/канала RabbitMQ.
# Это позволяет повторно использовать соединения и избегать частого их создания.
_kafka_producer = None
_rabbitmq_connection = None
_rabbitmq_channel = None

def delivery_report(err, msg):
    """ 
    Callback-функция, вызываемая для каждого сообщения, отправленного в Kafka,
    для указания результата доставки. Активируется вызовами poll() или flush().
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
        # Если используется режим мокирования
        # Упрощенная проверка: если _kafka_producer не является нашим кастомным моком, создаем его.
        if _kafka_producer is None or not getattr(_kafka_producer, '_is_custom_kafka_mock', False):
            # Создаем MagicMock без spec_set, чтобы свободно назначать атрибуты.
            _kafka_producer = MagicMock(name="GlobalMockKafkaProducer")
            # Явно определяем методы flush, produce и poll на мок-объекте _kafka_producer.
            _kafka_producer.flush = MagicMock(return_value=0, name="MockedFlushMethod")
            _kafka_producer.produce = MagicMock(name="MockedProduceMethod")
            _kafka_producer.poll = MagicMock(return_value=0, name="MockedPollMethod")
            _kafka_producer._is_custom_kafka_mock = True # Помечаем как наш кастомный мок
            logger.info("Global _kafka_producer initialized in MOCK mode (from get_kafka_producer) with explicit flush, produce, poll methods.")
        return _kafka_producer

    if _kafka_producer is None:
        try:
            # Конфигурация для продюсера Confluent Kafka
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all', # Ожидать подтверждения от всех синхронизированных реплик (ISR)
                'retries': 3,   # Количество попыток повторной отправки, прежде чем считать сообщение недоставленным
                'linger.ms': 10 # Ожидать до 10 мс для группировки сообщений в пакеты
                # 'message.timeout.ms': 30000 # Опционально: таймаут для запроса продюсера
            }
            _kafka_producer = ConfluentKafkaProducer_actual(conf) # Также используем псевдоним здесь
            logger.info(f"Confluent Kafka producer initialized with config: {conf}")
        except KafkaException as e: # Ловим общие KafkaException из confluent-kafka
            logger.error(f"Failed to initialize Confluent Kafka producer: {e}")
            _kafka_producer = None # Продюсер остается None в случае ошибки
    return _kafka_producer

def send_kafka_message(topic, message_dict):
    """
    Отправляет сообщение в указанный топик Kafka.

    Args:
        topic (str): Имя топика Kafka.
        message_dict (dict): Словарь с сообщением, который будет сериализован в JSON.

    Returns:
        bool: True, если сообщение успешно передано для отправки (доставка асинхронна),
              False в случае ошибки.
    """
    producer = get_kafka_producer()
    if producer:
        try:
            json_str = json.dumps(message_dict) # Сериализуем словарь в строку JSON
            value_bytes = json_str.encode('utf-8') # Кодируем строку в байты UTF-8
            
            # Асинхронная отправка сообщения. delivery_report будет вызван позже.
            producer.produce(topic, value=value_bytes, callback=delivery_report)
            
            # poll() для обслуживания обратных вызовов доставки (и других).
            # Небольшой неблокирующий опрос часто достаточен после каждого produce.
            # Высокопроизводительные приложения могут потребовать выделенного потока для опроса.
            producer.poll(0) 
            # logger.debug(f"Message passed for sending to Kafka topic {topic}: {message_dict}") # Логируем перед отчетом о доставке
            return True # Указывает, что сообщение передано для отправки (доставка асинхронна)
        except KafkaException as e: # Специфичные для Kafka ошибки
            logger.error(f"Failed to pass message for sending to Kafka topic {topic}: {e}")
            return False
        except BufferError as e: # confluent_kafka.Producer.produce может выбросить BufferError, если очередь продюсера заполнена
            logger.error(f"Kafka producer queue is full. Message to topic {topic} not sent: {message_dict}. Error: {e}")
            # Опционально, можно вызвать poll() здесь, чтобы попытаться освободить место, затем повторить,
            # или обработать как ошибку.
            # producer.poll(1) # Опрашиваем недолго, чтобы очистить очередь
            return False
        except Exception as e: # Ловим любые другие неожиданные ошибки
            logger.error(f"An unexpected error occurred while sending Kafka message to topic {topic}: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"Kafka producer is not available. Message to topic {topic} not sent: {message_dict}")
        return False

def get_rabbitmq_channel():
    logger.info(f"get_rabbitmq_channel: USE_MOCKS environment variable is currently '{os.getenv('USE_MOCKS')}' (type: {type(os.getenv('USE_MOCKS'))})") 
    """
    Возвращает глобальный экземпляр канала RabbitMQ.
    Если переменная окружения USE_MOCKS установлена в "true", возвращает мок-объект.
    При первом вызове (или если соединение/канал закрыты), устанавливает соединение
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
        # Если соединение не установлено или закрыто
        if _rabbitmq_connection is None or _rabbitmq_connection.is_closed:
            _rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST) # Параметры соединения
            )
            _rabbitmq_channel = _rabbitmq_connection.channel() # Открываем канал
            logger.info(f"RabbitMQ connection established ({RABBITMQ_HOST}), channel opened.")
            # Объявляем очереди как устойчивые (переживут перезапуск брокера)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"RabbitMQ queues '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' and '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' declared.")

        # Если канал не открыт или закрыт (может случиться, если соединение осталось, но канал закрылся)
        if _rabbitmq_channel is None or _rabbitmq_channel.is_closed:
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info("RabbitMQ channel was reopened.")
            # Повторно объявляем очереди на случай, если они не были объявлены ранее или канал новый
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)

    except pika.exceptions.AMQPConnectionError as e: # Ошибка соединения RabbitMQ
        logger.error(f"Failed to connect to RabbitMQ or declare queue: {e}")
        _rabbitmq_connection = None
        _rabbitmq_channel = None
    return _rabbitmq_channel

def publish_rabbitmq_message(exchange_name, routing_key, body):
    """
    Публикует сообщение в RabbitMQ.

    Args:
        exchange_name (str): Имя обменника. Используйте '' для отправки напрямую в очередь.
        routing_key (str): Ключ маршрутизации (обычно имя очереди при прямой отправке).
        body (dict): Словарь с сообщением, который будет сериализован в JSON.

    Returns:
        bool: True, если сообщение успешно опубликовано, False в случае ошибки.
    """
    channel = get_rabbitmq_channel()
    if channel:
        try:
            channel.basic_publish(
                exchange=exchange_name, # Имя обменника
                routing_key=routing_key, # Ключ маршрутизации (имя очереди)
                body=json.dumps(body).encode('utf-8'), # Тело сообщения (JSON -> байты)
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Делаем сообщение постоянным (переживет перезапуск брокера)
                )
            )
            logger.debug(f"Message published to RabbitMQ, exchange '{exchange_name}', routing key '{routing_key}': {body}")
            return True
        except Exception as e: # Любая ошибка во время публикации
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
            global _rabbitmq_channel # Помечаем канал как недействительный, чтобы он был пересоздан при следующем вызове
            _rabbitmq_channel = None 
            return False
    else:
        logger.warning(f"RabbitMQ channel is not available. Message for exchange '{exchange_name}', routing key '{routing_key}' not sent: {body}")
        return False

def close_rabbitmq_connection():
    """ Закрывает канал и соединение RabbitMQ, если они открыты. """
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
    Очищает все сообщения из очереди продюсера Kafka и освобождает ресурсы.
    Продюсер Confluent Kafka не имеет явного метода close(), очистка и
    обнуление ссылки позволяют сборщику мусора освободить ресурсы.
    """
    global _kafka_producer
    if _kafka_producer is not None:
        # Проверяем, является ли _kafka_producer специальным моком, который не должен вызывать flush.
        # Это моки, созданные get_kafka_producer(), когда USE_MOCKS="true",
        # или те, которые явно установлены в тестах как простые MagicMock без намерения тестировать flush.
        is_simple_placeholder_mock = isinstance(_kafka_producer, MagicMock) and \
                                     getattr(_kafka_producer, '_is_custom_kafka_mock', False) is True # Проверяем явное True

        if is_simple_placeholder_mock:
            logger.info(f"Kafka mock producer '{_kafka_producer._extract_mock_name()}' (marked as _is_custom_kafka_mock) nulled without calling flush.")
            _kafka_producer = None
            return

        # Для всех остальных случаев (реальный продюсер или мок реального продюсера из @patch)
        # пытаемся вызвать flush.
        try:
            # Ожидаем отправки всех сообщений в очереди продюсера.
            # Таймаут - это максимальное время ожидания отправки ВСЕХ сообщений,
            # а не каждого сообщения по отдельности.
            logger.info(f"Attempting to call flush() for producer: {_kafka_producer}")
            remaining_messages = _kafka_producer.flush(timeout=10) # таймаут в секундах
            if remaining_messages > 0:
                logger.warning(f"{remaining_messages} Kafka messages still in queue after flush timeout.")
            else:
                logger.info("All Kafka messages successfully flushed.")
        except KafkaException as e: # Общая ошибка Kafka во время flush
            logger.error(f"Error flushing Confluent Kafka producer: {e}")
        except Exception as e: # Любая другая неожиданная ошибка во время flush
            logger.error(f"An unexpected error occurred while flushing Kafka producer: {e}", exc_info=True)
        
        _kafka_producer = None 
        logger.info("Kafka producer resources released (set to None) after flush attempt or error.")


def cleanup_message_brokers():
    """ Выполняет очистку всех соединений с брокерами сообщений. """
    logger.info("Cleaning up message broker connections...")
    close_kafka_producer()
    close_rabbitmq_connection()

# Пример использования и тест, если модуль запускается напрямую.
if __name__ == '__main__':
    # Настройка базового логирования для тестового запуска.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    logger.info("--- Confluent Kafka Producer Test ---")
    kafka_prod_instance = get_kafka_producer()
    if kafka_prod_instance:
        test_message = {"event_type": "test_event", "detail": "Confluent Kafka is working!"}
        if send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, test_message):
            logger.info(f"Test message sent to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}: {test_message}")
        else:
            logger.error(f"Failed to send test message to {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}.")
        # В реальном приложении flush может вызываться реже или только при завершении работы.
        # Для этого теста мы вызываем его, чтобы обеспечить попытки доставки для тестового сообщения.
        # kafka_prod_instance.flush(timeout=5) # Очищается в close_kafka_producer
    else:
        logger.error("Confluent Kafka producer could not be initialized for test.")

    logger.info("--- RabbitMQ Channel Test ---")
    rmq_chan_instance = get_rabbitmq_channel()
    if rmq_chan_instance:
        logger.info(f"RabbitMQ channel obtained: {rmq_chan_instance}")
        if publish_rabbitmq_message(
            exchange_name='', # Пустая строка для обменника по умолчанию (отправка напрямую в очередь)
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, # Имя очереди как ключ маршрутизации
            body={"command": "test_command", "payload": "RabbitMQ is working!"}
        ):
            logger.info("Test message published to RabbitMQ.")
        else:
            logger.error("Failed to publish test message to RabbitMQ.")
    else:
        logger.error("RabbitMQ channel could not be obtained for test.")
        
    cleanup_message_brokers() # Очистка соединений после тестов
    logger.info("Test script finished.")
