# tests/unit/test_message_broker_clients.py
# Этот файл содержит модульные тесты для клиентов брокеров сообщений,
# в частности для функций, связанных с Kafka, определенных в core.message_broker_clients.
import unittest
from unittest.mock import MagicMock, patch, call # Инструменты для мокирования
import json # Для работы с JSON-сообщениями
import os # Для работы с переменными окружения (не используется напрямую в этих тестах, но может быть полезно)

# Импортируем функции и классы для тестирования.
# Предполагается, что core.message_broker_clients находится в PYTHONPATH.
# Для надежного тестирования убедитесь, что PYTHONPATH настроен правильно,
# или скорректируйте путь импорта.
import core.message_broker_clients # Импортируем модуль целиком для доступа к глобальным переменным
from core.message_broker_clients import (
    get_kafka_producer,         # Функция получения продюсера Kafka
    send_kafka_message,         # Функция отправки сообщения Kafka
    close_kafka_producer,       # Функция закрытия продюсера Kafka
    delivery_report,            # Callback-функция для отчета о доставке (также тестируема)
    KAFKA_BOOTSTRAP_SERVERS,    # Используется для конфигурации продюсера
    _kafka_producer as global_kafka_producer # Глобальная переменная продюсера для проверок очистки
)

# Мокирование класса Producer из confluent_kafka.
# Декоратор @patch на уровне класса был удален; вместо этого используется @patch в каждом методе
# или контекстный менеджер `with patch(...)` для большей гибкости и ясности.
class TestKafkaClientConfluent(unittest.TestCase):
    """
    Набор тестов для функций клиента Kafka, использующих библиотеку confluent-kafka.
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Сбрасывает глобальный продюсер Kafka для обеспечения изоляции тестов.
        Доступ к переменной уровня модуля для сброса.
        """
        core.message_broker_clients._kafka_producer = None

    def tearDown(self):
        """
        Очистка после каждого теста.
        Закрывает глобальный продюсер Kafka и явно устанавливает его в None.
        Вызывает реальную функцию close_kafka_producer для проверки ее логики.
        """
        # Если глобальный продюсер был мокирован, и у него есть мок-метод flush,
        # убедимся, что он возвращает 0 (нет оставшихся сообщений) для корректного завершения.
        if isinstance(core.message_broker_clients._kafka_producer, MagicMock):
            if hasattr(core.message_broker_clients._kafka_producer, 'flush') and \
               isinstance(core.message_broker_clients._kafka_producer.flush, MagicMock):
                core.message_broker_clients._kafka_producer.flush.return_value = 0
        
        close_kafka_producer() # Вызываем реальную функцию закрытия
        # Явно устанавливаем в None на случай, если close_kafka_producer был мокирован или не сработал.
        core.message_broker_clients._kafka_producer = None

    # Декоратор @patch('core.message_broker_clients.Producer') УБРАН для этого теста,
    # чтобы проверить логику USE_MOCKS="true" без того, чтобы Producer уже был моком.
    def test_get_kafka_producer_creates_producer(self): # MockProducer убран из аргументов
        """
        Тест: get_kafka_producer создает экземпляр Producer или мок.
        Когда USE_MOCKS="true", он должен создать кастомный мок.
        Когда USE_MOCKS="false", он должен создать реальный Producer (который мы мокируем локально).
        """
        if os.environ.get("USE_MOCKS") == "true":
            producer = get_kafka_producer() # Первый вызов должен создать мок-продюсера
            self.assertIsNotNone(producer, "Продюсер не должен быть None.")
            self.assertIsInstance(producer, MagicMock, "Продюсер должен быть MagicMock, когда USE_MOCKS='true'.")
            self.assertTrue(getattr(producer, '_is_custom_kafka_mock', False), "Продюсер должен быть помечен как _is_custom_kafka_mock.")
            self.assertIs(producer, core.message_broker_clients._kafka_producer, "Возвращенный продюсер должен быть глобальным мок-продюсером.")
            # Текущая реализация get_kafka_producer для USE_MOCKS="true" не использует spec, поэтому _spec_class не проверяется.

        else: # USE_MOCKS не "true"
            # Для этого пути нам нужно мокировать 'core.message_broker_clients.ConfluentKafkaProducer_actual',
            # чтобы не создавать реального продюсера. Используем локальный контекстный менеджер.
            with patch('core.message_broker_clients.ConfluentKafkaProducer_actual') as MockProducerLocal:
                mock_producer_instance = MockProducerLocal.return_value # Мок экземпляра продюсера
                # Явно задаем поведение атрибута _is_custom_kafka_mock для мока реального продюсера.
                # Это предотвратит авто-создание MagicMock для этого атрибута, который является truthy.
                mock_producer_instance._is_custom_kafka_mock = False

                producer = get_kafka_producer() # Первый вызов должен создать продюсера
                
                self.assertIsNotNone(producer, "Продюсер не должен быть None.")
                self.assertIs(producer, mock_producer_instance, "Возвращенный продюсер не является мок-экземпляром.")
                # Теперь можно напрямую проверять значение, так как оно было явно установлено.
                self.assertIs(producer._is_custom_kafka_mock, False,
                              "Мок реального продюсера (из creates_producer) _is_custom_kafka_mock должен быть явно False")
                
                # Ожидаемая конфигурация для продюсера
                expected_config = {
                    'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS, # Адрес серверов Kafka
                    'acks': 'all',                                # Подтверждение от всех реплик
                    'retries': 3,                                 # Количество попыток повторной отправки
                    'linger.ms': 10                               # Задержка для группировки сообщений
                }
                MockProducerLocal.assert_called_once_with(expected_config) # Проверяем, что конструктор Producer вызван с этой конфигурацией

    # Декоратор @patch('core.message_broker_clients.Producer') УБРАН для этого теста.
    def test_get_kafka_producer_returns_existing_producer(self): # MockProducer убран из аргументов
        """
        Тест: get_kafka_producer возвращает существующий экземпляр Producer при повторных вызовах.
        Проверяет, что конструктор Producer вызывается только один раз (для USE_MOCKS="false").
        """
        # Первый вызов создает продюсера (или мок)
        first_producer = get_kafka_producer()
        # Второй вызов должен вернуть тот же самый экземпляр
        second_producer = get_kafka_producer()
        
        self.assertIs(first_producer, second_producer, "Повторный вызов get_kafka_producer должен возвращать тот же экземпляр.")

        if os.environ.get("USE_MOCKS") == "true":
            self.assertTrue(getattr(first_producer, '_is_custom_kafka_mock', False), "Продюсер должен быть помечен как _is_custom_kafka_mock.")
            # Когда USE_MOCKS="true", get_kafka_producer() создает свой внутренний мок.
            # Реальный core.message_broker_clients.ConfluentKafkaProducer_actual не должен вызываться для создания экземпляра.
        else: # USE_MOCKS не "true"
            # Для этого пути нам нужно мокировать 'core.message_broker_clients.ConfluentKafkaProducer_actual',
            # чтобы проверить, что он был вызван только один раз (при первом вызове get_kafka_producer).
            # Это требует, чтобы первый get_kafka_producer() был сделан ВНУТРИ этого блока patch.
            core.message_broker_clients._kafka_producer = None # Сброс перед тестом этого пути
            with patch('core.message_broker_clients.ConfluentKafkaProducer_actual') as MockProducerLocalContext:
                # Явно задаем поведение атрибута _is_custom_kafka_mock для мока реального продюсера.
                MockProducerLocalContext.return_value._is_custom_kafka_mock = False

                # Первый вызов создает продюсера
                producer_call_1 = get_kafka_producer()
                # Второй вызов должен вернуть тот же самый экземпляр
                producer_call_2 = get_kafka_producer()

                self.assertIs(producer_call_1, producer_call_2, "Повторный вызов get_kafka_producer должен возвращать тот же экземпляр (когда USE_MOCKS=false).")
                # Теперь можно напрямую проверять значение.
                self.assertIs(producer_call_1._is_custom_kafka_mock, False,
                              "Мок реального продюсера (из returns_existing_producer) _is_custom_kafka_mock должен быть явно False")
                MockProducerLocalContext.assert_called_once() # Конструктор Producer должен быть вызван только один раз


    # Декораторы удалены. Тест теперь проверяет путь USE_MOCKS="true".
    def test_send_kafka_message_success(self):
        """
        Тест успешной отправки сообщения Kafka (когда USE_MOCKS="true").
        Проверяет, что get_kafka_producer возвращает мок, и его методы produce/poll вызываются.
        """
        with patch.dict(os.environ, {"USE_MOCKS": "true"}, clear=True):
            core.message_broker_clients._kafka_producer = None # Сброс перед тестом
            
            producer_mock = get_kafka_producer()
            self.assertTrue(getattr(producer_mock, '_is_custom_kafka_mock', False))

            producer_mock.produce.reset_mock()
            producer_mock.poll.reset_mock() # Если poll используется

            topic = "test_topic"
            message_dict = {"key": "value", "num": 123}
            expected_value_bytes = json.dumps(message_dict).encode('utf-8')

            # Мокируем delivery_report, так как send_kafka_message передает его как callback
            with patch('core.message_broker_clients.delivery_report') as mock_delivery_cb:
                result = send_kafka_message(topic, message_dict)
                self.assertTrue(result, "send_kafka_message должна возвращать True при успешном начале отправки.")

                producer_mock.produce.assert_called_once_with(
                    topic,
                    value=expected_value_bytes,
                    callback=mock_delivery_cb 
                )
                # Проверяем вызов poll
                producer_mock.poll.assert_called_once_with(0) 

    # Декоратор удален. Тест теперь проверяет путь USE_MOCKS="false".
    def test_send_kafka_message_no_producer_after_init_failure(self):
        """
        Тест: send_kafka_message (когда USE_MOCKS="false") корректно обрабатывает ошибку создания продюсера.
        Проверяет, что возвращается False, и была попытка создать реальный продюсер.
        """
        # Этот тест должен выполняться с USE_MOCKS="false"
        with patch.dict(os.environ, {"USE_MOCKS": "false"}, clear=True):
            core.message_broker_clients._kafka_producer = None # Сброс глобального продюсера

            # Патчим ConfluentKafkaProducer_actual (реальный класс) так, чтобы его конструктор вызывал ошибку
            with patch('core.message_broker_clients.ConfluentKafkaProducer_actual', 
                       side_effect=core.message_broker_clients.KafkaException("Test KProducer Init Error")) as mock_real_producer_class:
                
                result = send_kafka_message("any_topic_init_fail", {"key": "value"})
                
                self.assertFalse(result, "send_kafka_message должна вернуть False, если продюсер не удалось создать.")
                mock_real_producer_class.assert_called_once() # Проверяем, что была попытка создать реальный продюсер
                self.assertIsNone(core.message_broker_clients._kafka_producer, "Глобальный продюсер должен оставаться None после ошибки инициализации.")
                # Можно также проверить лог предупреждения/ошибки, если это важно.

    @patch('core.message_broker_clients.ConfluentKafkaProducer_actual') # Патчим реальный класс для этого теста
    def test_close_kafka_producer_flushes_or_skips_for_mock(self, MockProducer): # MockProducer здесь это ConfluentKafkaProducer_actual
        """
        Тест: close_kafka_producer вызывает flush у реального продюсера,
        но пропускает flush для MagicMock (помеченного как _is_custom_kafka_mock) и просто обнуляет.
        Проверяет, что глобальный продюсер обнуляется в обоих случаях.
        """
        # Сценарий 1: _kafka_producer является MagicMock, помеченным как _is_custom_kafka_mock.
        # Это имитирует поведение, когда USE_MOCKS=true или мок создан вручную для пропуска логики.
        mock_producer_custom_magic_mock = MagicMock()
        mock_producer_custom_magic_mock.flush = MagicMock(return_value=0) # На всякий случай, если бы он вызывался
        mock_producer_custom_magic_mock._is_custom_kafka_mock = True # Ключевая пометка
        
        core.message_broker_clients._kafka_producer = mock_producer_custom_magic_mock
        close_kafka_producer()
        
        # Для MagicMock, помеченного как _is_custom_kafka_mock, flush не должен вызываться
        mock_producer_custom_magic_mock.flush.assert_not_called()
        self.assertIsNone(core.message_broker_clients._kafka_producer, "Глобальный продюсер (кастомный MagicMock) должен быть None после закрытия.")

        # Сценарий 2: _kafka_producer является "реальным" моком от @patch (экземпляр MockProducer).
        # Он НЕ должен иметь атрибут _is_custom_kafka_mock = True.
        # В этом случае flush должен вызываться.
        core.message_broker_clients._kafka_producer = None # Сброс перед следующим сценарием
        
        # Создаем новый мок для этого сценария, чтобы счетчики вызовов были чистыми
        mock_real_producer_instance = MockProducer.return_value 
        # Убедимся, что мок реального продюсера не помечен как custom mock.
        # getattr вернет None если атрибут не существует (или значение по умолчанию), мы проверяем, что он не True.
        self.assertNotEqual(getattr(mock_real_producer_instance, '_is_custom_kafka_mock', None), True,
                             "Мок реального продюсера не должен быть помечен как _is_custom_kafka_mock=True для этого сценария.")

        mock_real_producer_instance.flush.return_value = 0 # Настраиваем возвращаемое значение для flush
        core.message_broker_clients._kafka_producer = mock_real_producer_instance
        
        close_kafka_producer() # Вызываем функцию, которая теперь должна вызвать flush
        
        mock_real_producer_instance.flush.assert_called_once_with(timeout=10)
        self.assertIsNone(core.message_broker_clients._kafka_producer, "Глобальный продюсер (реальный мок) должен быть None после закрытия.")

    # Эти тесты предназначены для непосредственного юнит-тестирования самой callback-функции delivery_report.
    # @patch('core.message_broker_clients.Producer') здесь не нужен, так как мы тестируем delivery_report изолированно.
    def test_delivery_report_success_direct_call(self): 
        """
        Тест callback-функции delivery_report при успешной доставке сообщения.
        """
        mock_msg = MagicMock() # Мок для объекта сообщения Kafka
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 100
        
        with patch('core.message_broker_clients.logger') as mock_logger: # Мокируем логгер
            delivery_report(None, mock_msg) # err равен None при успехе
            mock_logger.debug.assert_called_once_with(
                f"Message delivered to topic my_topic partition 0 offset 100"
            )

    def test_delivery_report_failure_direct_call(self):
        """
        Тест callback-функции delivery_report при ошибке доставки сообщения.
        """
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "my_topic"
        mock_msg.partition.return_value = 1
        err_message = "Broker: Message timed out" # Пример сообщения об ошибке
        
        with patch('core.message_broker_clients.logger') as mock_logger:
            delivery_report(err_message, mock_msg) # err не None при ошибке
            mock_logger.error.assert_called_once_with(
                f"Message delivery failed for topic my_topic partition 1: {err_message}"
            )

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()
