# core/message_broker_clients.py
# Этот модуль предоставляет клиенты для взаимодействия с брокерами сообщений Kafka и RabbitMQ.
# Он включает функции для получения продюсера Kafka, канала RabbitMQ, отправки сообщений
# и очистки соединений. Также поддерживает режим мокирования для тестов.

import json
import logging
import os
import pika # Библиотека для работы с RabbitMQ
from confluent_kafka import Producer, KafkaException # KafkaError as ConfluentKafkaError (ConfluentKafkaError не используется напрямую, KafkaException шире)
from unittest.mock import MagicMock # Используется для мокирования в тестах

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
_kafka_producer = None
_rabbitmq_connection = None
_rabbitmq_channel = None

def delivery_report(err, msg):
    """ 
    Callback-функция, вызываемая для каждого сообщения, отправленного в Kafka,
    чтобы указать результат доставки. Активируется вызовами poll() или flush().
    """
    if err is not None:
        logger.error(f"Ошибка доставки сообщения в топик {msg.topic()} раздел {msg.partition()}: {err}")
    else:
        logger.debug(f"Сообщение доставлено в топик {msg.topic()} раздел {msg.partition()} смещение {msg.offset()}")

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
        if not (isinstance(_kafka_producer, MagicMock) and hasattr(_kafka_producer, '_is_custom_kafka_mock')):
            # Если _kafka_producer еще не является нашим кастомным моком, создаем его.
            _kafka_producer = MagicMock(name="GlobalMockKafkaProducer")
            _kafka_producer.produce = MagicMock(name="MockKafkaProducer.produce")
            _kafka_producer.flush = MagicMock(name="MockKafkaProducer.flush", return_value=0) # flush возвращает количество сообщений в очереди
            _kafka_producer._is_custom_kafka_mock = True # Помечаем его как наш кастомный мок
            logger.info("Глобальный _kafka_producer инициализирован в режиме MOCK (из get_kafka_producer).") # Added clarity
        return _kafka_producer

    if _kafka_producer is None:
        try:
            # Конфигурация для продюсера Confluent Kafka
            conf = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'acks': 'all', # Ждать подтверждения от всех реплик в ISR (in-sync replicas)
                'retries': 3,   # Количество попыток повторной отправки перед тем, как считать сообщение недоставленным
                'linger.ms': 10 # Ожидание до 10 мс для группировки сообщений в батчи
                # 'message.timeout.ms': 30000 # Опционально: таймаут для запроса продюсера
            }
            _kafka_producer = Producer(conf)
            logger.info(f"Продюсер Confluent Kafka инициализирован с конфигурацией: {conf}")
        except KafkaException as e: # Перехватываем общую ошибку KafkaException от confluent-kafka
            logger.error(f"Не удалось инициализировать продюсер Confluent Kafka: {e}")
            _kafka_producer = None # В случае ошибки продюсер остается None
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
            # logger.debug(f"Сообщение передано на отправку в топик Kafka {topic}: {message_dict}") # Лог перед отчетом о доставке
            return True # Указывает, что сообщение было передано на отправку (доставка асинхронна)
        except KafkaException as e: # Ошибки, специфичные для Kafka
            logger.error(f"Не удалось передать сообщение на отправку в топик Kafka {topic}: {e}")
            return False
        except BufferError as e: # confluent_kafka.Producer.produce может вызвать BufferError, если очередь продюсера заполнена
            logger.error(f"Очередь продюсера Kafka заполнена. Сообщение в топик {topic} не отправлено: {message_dict}. Ошибка: {e}")
            # Опционально, можно вызвать poll() здесь, чтобы попытаться освободить место, а затем повторить,
            # или обработать как сбой.
            # producer.poll(1) # Опросить в течение короткого времени, чтобы очистить очередь
            return False
        except Exception as e: # Перехват любых других неожиданных ошибок
            logger.error(f"Произошла неожиданная ошибка при отправке сообщения Kafka в топик {topic}: {e}", exc_info=True)
            return False
    else:
        logger.warning(f"Продюсер Kafka недоступен. Сообщение в топик {topic} не отправлено: {message_dict}")
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
            logger.info("Глобальные _rabbitmq_channel и _rabbitmq_connection инициализированы в режиме MOCK.")
        return _rabbitmq_channel

    try:
        # Если соединение не установлено или закрыто
        if _rabbitmq_connection is None or _rabbitmq_connection.is_closed:
            _rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST) # Параметры соединения
            )
            _rabbitmq_channel = _rabbitmq_connection.channel() # Открываем канал
            logger.info(f"Соединение с RabbitMQ установлено ({RABBITMQ_HOST}), канал открыт.")
            # Объявляем очереди как durable (устойчивые к перезапуску брокера)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)
            logger.info(f"Очереди RabbitMQ '{RABBITMQ_QUEUE_PLAYER_COMMANDS}' и '{RABBITMQ_QUEUE_MATCHMAKING_EVENTS}' объявлены.")

        # Если канал не открыт или закрыт (может произойти, если соединение осталось, а канал закрылся)
        if _rabbitmq_channel is None or _rabbitmq_channel.is_closed:
            _rabbitmq_channel = _rabbitmq_connection.channel()
            logger.info("Канал RabbitMQ был переоткрыт.")
            # Повторно объявляем очереди на случай, если они не были объявлены ранее или канал новый
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_PLAYER_COMMANDS, durable=True)
            _rabbitmq_channel.queue_declare(queue=RABBITMQ_QUEUE_MATCHMAKING_EVENTS, durable=True)

    except pika.exceptions.AMQPConnectionError as e: # Ошибка соединения с RabbitMQ
        logger.error(f"Не удалось подключиться к RabbitMQ или объявить очередь: {e}")
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
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE # Делаем сообщение устойчивым (сохраняется при перезапуске брокера)
                )
            )
            logger.debug(f"Сообщение опубликовано в RabbitMQ, exchange '{exchange_name}', routing_key '{routing_key}': {body}")
            return True
        except Exception as e: # Любая ошибка при публикации
            logger.error(f"Не удалось опубликовать сообщение в RabbitMQ: {e}")
            global _rabbitmq_channel # Помечаем канал как недействительный, чтобы он был пересоздан при следующем вызове
            _rabbitmq_channel = None 
            return False
    else:
        logger.warning(f"Канал RabbitMQ недоступен. Сообщение для exchange '{exchange_name}', routing_key '{routing_key}' не отправлено: {body}")
        return False

def close_rabbitmq_connection():
    """ Закрывает канал и соединение RabbitMQ, если они открыты. """
    global _rabbitmq_connection, _rabbitmq_channel
    if _rabbitmq_channel is not None and _rabbitmq_channel.is_open:
        try:
            _rabbitmq_channel.close()
            logger.info("Канал RabbitMQ закрыт.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии канала RabbitMQ: {e}")
    if _rabbitmq_connection is not None and _rabbitmq_connection.is_open:
        try:
            _rabbitmq_connection.close()
            logger.info("Соединение с RabbitMQ закрыто.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии соединения с RabbitMQ: {e}")
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
        # Это моки, созданные get_kafka_producer() при USE_MOCKS="true",
        # или те, что явно установлены в тестах как простые MagicMock без намерения тестировать flush.
        is_simple_placeholder_mock = isinstance(_kafka_producer, MagicMock) and \
                                     getattr(_kafka_producer, '_is_custom_kafka_mock', False) is True # Check for explicit True

        if is_simple_placeholder_mock:
            logger.info(f"Мок-продюсер Kafka '{_kafka_producer._extract_mock_name()}' (помечен как _is_custom_kafka_mock) обнулен без вызова flush.")
            _kafka_producer = None
            return

        # Для всех остальных случаев (реальный продюсер или мок реального продюсера от @patch)
        # пытаемся вызвать flush.
        try:
            # Ожидание отправки всех сообщений из очереди продюсера.
            # Таймаут - это максимальное время ожидания отправки ВСЕХ сообщений,
            # а не для каждого сообщения в отдельности.
            logger.info(f"Попытка вызова flush() для продюсера: {_kafka_producer}") # Added for clarity
            remaining_messages = _kafka_producer.flush(timeout=10) # таймаут в секундах
            if remaining_messages > 0:
                logger.warning(f"{remaining_messages} сообщений Kafka все еще в очереди после таймаута flush.")
            else:
                logger.info("Все сообщения Kafka успешно сброшены (flushed).")
        except KafkaException as e: # Общая ошибка Kafka при flush
            logger.error(f"Ошибка при сбросе (flush) продюсера Confluent Kafka: {e}")
        except Exception as e: # Любая другая неожиданная ошибка во время flush
            logger.error(f"Произошла неожиданная ошибка во время сброса (flush) продюсера Kafka: {e}", exc_info=True)
        
        _kafka_producer = None 
        logger.info("Ресурсы продюсера Kafka освобождены (установлен в None) после попытки flush или ошибки.")


def cleanup_message_brokers():
    """ Выполняет очистку всех соединений с брокерами сообщений. """
    logger.info("Очистка соединений с брокерами сообщений...")
    close_kafka_producer()
    close_rabbitmq_connection()

# Пример использования и тест, если модуль запускается напрямую.
if __name__ == '__main__':
    # Настройка базового логирования для тестового запуска.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    logger.info("--- Тест продюсера Confluent Kafka ---")
    kafka_prod_instance = get_kafka_producer()
    if kafka_prod_instance:
        test_message = {"event_type": "test_event", "detail": "Confluent Kafka работает!"}
        if send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, test_message):
            logger.info(f"Тестовое сообщение отправлено в {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}: {test_message}")
        else:
            logger.error(f"Не удалось отправить тестовое сообщение в {KAFKA_DEFAULT_TOPIC_GAME_EVENTS}.")
        # В реальном приложении flush может вызываться реже или только при завершении работы.
        # Для этого теста мы вызываем его, чтобы обеспечить попытки доставки тестового сообщения.
        # kafka_prod_instance.flush(timeout=5) # Сбрасывается в close_kafka_producer
    else:
        logger.error("Продюсер Confluent Kafka не может быть инициализирован для теста.")

    logger.info("--- Тест канала RabbitMQ ---")
    rmq_chan_instance = get_rabbitmq_channel()
    if rmq_chan_instance:
        logger.info(f"Канал RabbitMQ получен: {rmq_chan_instance}")
        if publish_rabbitmq_message(
            exchange_name='', # Пустая строка для default exchange (отправка напрямую в очередь)
            routing_key=RABBITMQ_QUEUE_PLAYER_COMMANDS, # Имя очереди как ключ маршрутизации
            body={"command": "test_command", "payload": "RabbitMQ работает!"}
        ):
            logger.info("Тестовое сообщение опубликовано в RabbitMQ.")
        else:
            logger.error("Не удалось опубликовать тестовое сообщение в RabbitMQ.")
    else:
        logger.error("Канал RabbitMQ не может быть получен для теста.")
        
    cleanup_message_brokers() # Очистка соединений после тестов
    logger.info("Тестовый скрипт завершен.")
