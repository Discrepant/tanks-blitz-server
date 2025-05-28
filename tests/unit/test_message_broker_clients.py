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

    @patch('core.message_broker_clients.Producer') # Мокируем класс Producer из модуля
    def test_get_kafka_producer_creates_producer(self, MockProducer):
        """
        Тест: get_kafka_producer создает экземпляр Producer, если он еще не существует.
        Проверяет, что Producer вызывается с правильной конфигурацией.
        """
        if os.environ.get("USE_MOCKS") == "true":
            producer = get_kafka_producer() # Первый вызов должен создать мок-продюсера
            self.assertIsNotNone(producer, "Продюсер не должен быть None.")
            self.assertIsInstance(producer, MagicMock, "Продюсер должен быть MagicMock, когда USE_MOCKS='true'.")
            self.assertTrue(getattr(producer, '_is_custom_kafka_mock', False), "Продюсер должен быть помечен как _is_custom_kafka_mock.")
            self.assertIs(producer, core.message_broker_clients._kafka_producer, "Возвращенный продюсер должен быть глобальным мок-продюсером.")
            MockProducer.assert_not_called() # Реальный конструктор не должен вызываться
        else:
            mock_producer_instance = MockProducer.return_value # Мок экземпляра продюсера
            producer = get_kafka_producer() # Первый вызов должен создать продюсера
            
            self.assertIsNotNone(producer, "Продюсер не должен быть None.")
            self.assertIs(producer, mock_producer_instance, "Возвращенный продюсер не является мок-экземпляром.")
            
            # Ожидаемая конфигурация для продюсера
            expected_config = {
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS, # Адрес серверов Kafka
                'acks': 'all',                                # Подтверждение от всех реплик
                'retries': 3,                                 # Количество попыток повторной отправки
                'linger.ms': 10                               # Задержка для группировки сообщений
            }
            MockProducer.assert_called_once_with(expected_config) # Проверяем, что конструктор Producer вызван с этой конфигурацией

    @patch('core.message_broker_clients.Producer')
    def test_get_kafka_producer_returns_existing_producer(self, MockProducer):
        """
        Тест: get_kafka_producer возвращает существующий экземпляр Producer при повторных вызовах.
        Проверяет, что конструктор Producer вызывается только один раз.
        """
        # Первый вызов создает продюсера
        first_producer = get_kafka_producer()
        # Второй вызов должен вернуть тот же самый экземпляр
        second_producer = get_kafka_producer()
        
        self.assertIs(first_producer, second_producer, "Повторный вызов get_kafka_producer должен возвращать тот же экземпляр.")

        if os.environ.get("USE_MOCKS") == "true":
            self.assertTrue(getattr(first_producer, '_is_custom_kafka_mock', False), "Продюсер должен быть помечен как _is_custom_kafka_mock.")
            MockProducer.assert_not_called() # Конструктор Producer не должен вызываться, когда USE_MOCKS='true' и продюсер уже создан.
        else:
            MockProducer.assert_called_once() # Конструктор Producer должен быть вызван только один раз

    # Используем вложенные декораторы @patch. Внешний (первый) мок передается последним аргументом.
    @patch('core.message_broker_clients.Producer')          # Внешний декоратор, mock_Producer будет mock_producer_class_arg
    @patch('core.message_broker_clients.delivery_report')   # Внутренний декоратор, mock_delivery_report будет mock_delivery_report_func_arg
    def test_send_kafka_message_success(self, mock_delivery_report_func_arg, mock_producer_class_arg):
        """
        Тест успешной отправки сообщения Kafka.
        Проверяет, что `producer.produce` и `producer.poll` вызываются корректно.
        """
        # mock_delivery_report_func_arg - это мок для функции delivery_report из модуля.
        # mock_producer_class_arg - это мок для класса Producer.
        
        mock_producer_instance = mock_producer_class_arg.return_value # Получаем мок экземпляра продюсера
        # Вручную устанавливаем глобальный продюсер в наш мок-экземпляр для этого теста,
        # так как get_kafka_producer внутри send_kafka_message будет его использовать.
        core.message_broker_clients._kafka_producer = mock_producer_instance
        
        topic = "test_topic"
        message_dict = {"key": "value", "num": 123}
        expected_value_bytes = json.dumps(message_dict).encode('utf-8') # Ожидаемые байты сообщения
        
        result = send_kafka_message(topic, message_dict) # Вызываем тестируемую функцию
        self.assertTrue(result, "send_kafka_message должна возвращать True при успешном начале отправки.")
        
        # Проверяем, что метод produce у продюсера был вызван с правильными аргументами
        mock_producer_instance.produce.assert_called_once_with(
            topic,
            value=expected_value_bytes,
            callback=core.message_broker_clients.delivery_report # Убеждаемся, что используется реальная callback-функция из модуля
        )
        mock_producer_instance.poll.assert_called_once_with(0) # Проверяем вызов poll

    @patch('core.message_broker_clients.Producer')
    def test_send_kafka_message_no_producer_after_init_failure(self, MockProducer):
        """
        Тест: send_kafka_message корректно обрабатывает ситуацию, когда продюсер не может быть создан.
        Проверяет, что возвращается False и глобальный продюсер остается None.
        """
        if os.environ.get("USE_MOCKS") == "true":
            # Когда USE_MOCKS=true, get_kafka_producer() всегда возвращает мок и не вызывает Producer(),
            # поэтому KafkaException не будет возбуждена таким образом.
            # Этот сценарий теста применим только когда USE_MOCKS не установлен в "true".
            # Можно либо пропустить тест, либо проверить, что send_kafka_message возвращает True,
            # так как мок-продюсер успешно используется.
            # Для сохранения цели теста (проверка обработки сбоя инициализации), мы его здесь не выполняем.
            # Вместо этого убедимся, что send_kafka_message работает с моком.
            core.message_broker_clients._kafka_producer = None # Reset to ensure get_kafka_producer is called
            producer = get_kafka_producer() # Should return the custom mock
            self.assertTrue(getattr(producer, '_is_custom_kafka_mock', False))
            
            # Попытка имитировать сбой внутри send_kafka_message, если get_kafka_producer вернул None (что не должно случиться при USE_MOCKS="true")
            # Этот участок кода проверяет, что если get_kafka_producer() вернул бы None, то send_kafka_message вернул бы False.
            # Но при USE_MOCKS="true", get_kafka_producer() не вернет None.
            with patch('core.message_broker_clients.get_kafka_producer', return_value=None) as mock_get_producer_None:
                 result_if_producer_is_none = send_kafka_message("test_topic_mock_fail", {"key": "value"})
                 self.assertFalse(result_if_producer_is_none, "send_kafka_message должна вернуть False, если get_kafka_producer вернул None.")
                 mock_get_producer_None.assert_called_once()
            return

        # Следующая логика выполняется только если USE_MOCKS не "true"
        # Имитируем сбой при создании продюсера, когда вызывается get_kafka_producer
        MockProducer.side_effect = core.message_broker_clients.KafkaException("Ошибка создания продюсера")
        
        # Убеждаемся, что _kafka_producer равен None, чтобы get_kafka_producer (вызываемый внутри send_kafka_message)
        # попытался его создать.
        core.message_broker_clients._kafka_producer = None 
        
        # Вызываем send_kafka_message. Это внутренне вызовет get_kafka_producer,
        # который попытается создать Producer (и потерпит неудачу).
        result = send_kafka_message("test_topic_fail", {"key": "value"})
        
        # Проверяем, что send_kafka_message корректно обработал сбой
        self.assertFalse(result, "send_kafka_message должна вернуть False, если продюсер не удалось создать.")
        
        # Проверяем, что была попытка создать Producer ровно один раз
        MockProducer.assert_called_once() 
        
        # Проверяем, что глобальный продюсер остается None после сбоя
        self.assertIsNone(core.message_broker_clients._kafka_producer, "Глобальный продюсер должен оставаться None после ошибки инициализации.")

    @patch('core.message_broker_clients.Producer')
    def test_close_kafka_producer_flushes_or_skips_for_mock(self, MockProducer): # Renamed for clarity
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
                f"Сообщение доставлено в топик my_topic раздел 0 смещение 100"
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
                f"Ошибка доставки сообщения в топик my_topic раздел 1: {err_message}"
            )

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()
