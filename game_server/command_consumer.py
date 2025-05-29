# game_server/command_consumer.py
# Этот модуль содержит классы для потребления сообщений из RabbitMQ:
# - PlayerCommandConsumer: обрабатывает команды игроков.
# - MatchmakingEventConsumer: обрабатывает события от системы матчмейкинга.
import json
import logging
import time
import os

import pika # Клиент для RabbitMQ
from pika.exceptions import AMQPConnectionError # Исключение при ошибке соединения с RabbitMQ

# Импортируем необходимые компоненты из других модулей проекта
from core.message_broker_clients import ( # Группируем импорты для ясности
    get_rabbitmq_channel, # Функция для получения канала RabbitMQ (не используется напрямую здесь, но может быть полезна)
    RABBITMQ_QUEUE_PLAYER_COMMANDS, # Имя очереди для команд игроков
    RABBITMQ_QUEUE_MATCHMAKING_EVENTS, # Имя очереди для событий матчмейкинга
    KAFKA_DEFAULT_TOPIC_GAME_EVENTS, # Топик Kafka для игровых событий
    send_kafka_message # Функция для отправки сообщений в Kafka
)
# Предполагается, что SessionManager и TankPool доступны для импорта
from game_server.session_manager import SessionManager 
from game_server.tank_pool import TankPool 

logger = logging.getLogger(__name__)

class PlayerCommandConsumer:
    """
    Потребитель команд игрока из RabbitMQ.

    Этот класс отвечает за подключение к RabbitMQ, получение сообщений с командами
    игроков, их обработку (например, вызов методов танка) и подтверждение сообщений.
    """
    def __init__(self, session_manager: SessionManager, tank_pool: TankPool):
        """
        Инициализирует потребителя команд игрока.

        Args:
            session_manager (SessionManager): Менеджер игровых сессий.
            tank_pool (TankPool): Пул объектов танков.
        """
        self.session_manager = session_manager
        self.tank_pool = tank_pool
        self.rabbitmq_channel = None # Канал RabbitMQ
        self.connection = None # Соединение с RabbitMQ
        # Убеждаемся, что переменные окружения извлекаются с значениями по умолчанию при необходимости
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost') # Хост RabbitMQ
        self.player_commands_queue = RABBITMQ_QUEUE_PLAYER_COMMANDS # Имя очереди команд
        self.rabbitmq_user = os.environ.get('RABBITMQ_USER', 'user')
        self.rabbitmq_password = os.environ.get('RABBITMQ_PASSWORD', 'password')

        self._connect_and_declare() # Подключаемся и объявляем очередь

    def _connect_and_declare(self):
        """
        Устанавливает соединение с RabbitMQ и объявляет очередь команд игроков.
        Включает механизм повторных попыток подключения в случае сбоя.
        """
        logger.info(f"PlayerCommandConsumer: Попытка подключения к RabbitMQ по адресу {self.rabbitmq_host}...")
        try:
            credentials = pika.PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_password)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    credentials=credentials,
                    heartbeat=600, # Поддерживать соединение активным
                    blocked_connection_timeout=300 # Таймаут для заблокированного соединения
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            # Объявляем очередь как durable (устойчивую к перезапуску брокера)
            self.rabbitmq_channel.queue_declare(queue=self.player_commands_queue, durable=True)
            # Обрабатывать по одному сообщению за раз (для равномерного распределения нагрузки, если есть несколько консьюмеров)
            self.rabbitmq_channel.basic_qos(prefetch_count=1) 
            logger.info(f"PlayerCommandConsumer: Успешное подключение к RabbitMQ и объявление очереди '{self.player_commands_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"PlayerCommandConsumer: Не удалось подключиться к RabbitMQ: {e}. Повторная попытка через 5 секунд...")
            time.sleep(5)
            self._connect_and_declare() # Рекурсивная попытка переподключения
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Произошла непредвиденная ошибка во время настройки RabbitMQ: {e}", exc_info=True)
            # В зависимости от политики, можно повторить попытку или вызвать исключение выше

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих сообщений из RabbitMQ.

        Декодирует сообщение, извлекает данные команды, находит соответствующий
        танк и вызывает его методы. Подтверждает сообщение после обработки.

        Args:
            ch: Канал RabbitMQ.
            method: Метаданные метода доставки.
            properties: Свойства сообщения.
            body (bytes): Тело сообщения (ожидается JSON).
        """
        try:
            logger.info(f"PlayerCommandConsumer: Получена команда через RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode()) # Декодируем JSON
            player_id = message_data.get("player_id")
            command = message_data.get("command")
            details = message_data.get("details", {}) # Детали команды, по умолчанию пустой словарь

            if not player_id or not command:
                logger.error("PlayerCommandConsumer: В сообщении отсутствуют player_id или command.")
                ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем сообщение, чтобы удалить его из очереди
                return

            session = self.session_manager.get_session_by_player_id(player_id)
            if not session:
                logger.warning(f"PlayerCommandConsumer: Игрок {player_id} не найден ни в одной сессии. Команда '{command}' проигнорирована.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            player_data = session.players.get(player_id)
            if not player_data:
                logger.warning(f"PlayerCommandConsumer: Данные игрока {player_id} не найдены в сессии {session.session_id}. Команда '{command}' проигнорирована.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank_id = player_data.get('tank_id')
            if not tank_id:
                logger.warning(f"PlayerCommandConsumer: ID танка не найден для игрока {player_id} в сессии {session.session_id}. Команда '{command}' проигнорирована.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            tank = self.tank_pool.get_tank(tank_id)
            if not tank:
                logger.warning(f"PlayerCommandConsumer: Танк {tank_id} для игрока {player_id} не найден в пуле. Команда '{command}' проигнорирована.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            logger.info(f"PlayerCommandConsumer: Обработка команды '{command}' для игрока {player_id}, танк {tank_id}.")

            if command == "shoot":
                tank.shoot() # Этот метод уже отправляет сообщение в Kafka
                # Дополнительная логика, связанная с результатом выстрела, может быть добавлена здесь
                logger.info(f"PlayerCommandConsumer: Танк {tank_id} выполнил команду 'shoot' для игрока {player_id}.")
            elif command == "move":
                # Предполагается, что 'details' содержит 'new_position'
                new_position = details.get("new_position")
                if new_position:
                    tank.move(tuple(new_position)) # Этот метод уже отправляет сообщение в Kafka
                    logger.info(f"PlayerCommandConsumer: Танк {tank_id} выполнил команду 'move' в {new_position} для игрока {player_id}.")
                else:
                    logger.warning(f"PlayerCommandConsumer: Отсутствует new_position в деталях команды 'move' для игрока {player_id}.")
            # Добавляйте обработчики других команд по мере необходимости
            # Пример:
            # elif command == "use_ability":
            #    ability_id = details.get("ability_id")
            #    if ability_id:
            #        # tank.use_ability(ability_id) # Предполагая, что такой метод существует
            #        logger.info(f"PlayerCommandConsumer: Танк {tank_id} использовал способность {ability_id} для игрока {player_id}.")
            #        # Отправка сообщения Kafka об использовании способности, если это не обрабатывается в методе танка
            #        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
            #            "event_type": "ability_used", "tank_id": tank.tank_id, 
            #            "ability_id": ability_id, "player_id": player_id, "timestamp": time.time()
            #        })
            #    else:
            #        logger.warning(f"PlayerCommandConsumer: Отсутствует ability_id в команде 'use_ability' для игрока {player_id}.")
            else:
                logger.warning(f"PlayerCommandConsumer: Получена неизвестная команда '{command}' для игрока {player_id}.")

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем успешную обработку

        except json.JSONDecodeError as e:
            logger.error(f"PlayerCommandConsumer: Не удалось декодировать JSON из сообщения: {body.decode()}. Ошибка: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем некорректное сообщение, чтобы удалить его
        except Exception as e:
            logger.exception(f"PlayerCommandConsumer: Непредвиденная ошибка при обработке сообщения RabbitMQ: {body.decode()}")
            # Повторная постановка сообщения в очередь (requeue) если это уместно, или отправка в DLQ (dead-letter queue).
            # Для простоты, мы подтверждаем сообщение, но в продакшене рассмотрите requeue или DLQ.
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Пример: отправить в DLQ, если настроено
            ch.basic_ack(delivery_tag=method.delivery_tag) # Пока просто подтверждаем


    def start_consuming(self):
        """
        Начинает потребление сообщений из очереди RabbitMQ.
        Включает механизм повторного подключения и перезапуска потребления в случае ошибок.
        """
        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.warning("PlayerCommandConsumer: Канал RabbitMQ не открыт. Попытка переподключения...")
            self._connect_and_declare() # Попытка переподключения
            if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed: # Проверяем снова
                logger.error("PlayerCommandConsumer: Не удалось переподключить канал RabbitMQ. Потребитель не может запуститься.")
                return

        logger.info(f"PlayerCommandConsumer: Начало потребления сообщений из '{self.player_commands_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.player_commands_queue,
            on_message_callback=self._callback
            # auto_ack=False # Уже по умолчанию, обеспечивает ручное подтверждение
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("PlayerCommandConsumer: Потребитель остановлен через KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"PlayerCommandConsumer: Ошибка потребителя: {e}. Попытка перезапуска потребления...", exc_info=True)
            # Потенциально можно добавить задержку и механизм повторных попыток здесь
            self.stop_consuming() # Очищаем текущее состояние
            time.sleep(5) # Ожидание перед повторной попыткой
            self.start_consuming() # Повторная попытка

    def stop_consuming(self):
        """
        Останавливает потребление сообщений и закрывает соединение с RabbitMQ.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("PlayerCommandConsumer: Остановка потребителя RabbitMQ...")
            try:
                self.rabbitmq_channel.stop_consuming() # Останавливаем потребление
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Ошибка при остановке потребления: {e}", exc_info=True)
            # Закрытие канала здесь может быть преждевременным, если соединение используется совместно.
            # Однако, если этот консьюмер управляет своим каналом эксклюзивно, то можно закрыть.
            # self.rabbitmq_channel.close() 
            logger.info("PlayerCommandConsumer: Потребитель RabbitMQ остановлен.")
        if self.connection and self.connection.is_open:
            logger.info("PlayerCommandConsumer: Закрытие соединения с RabbitMQ...")
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"PlayerCommandConsumer: Ошибка при закрытии соединения: {e}", exc_info=True)
            logger.info("PlayerCommandConsumer: Соединение с RabbitMQ закрыто.")

# Пример того, как это может быть запущено (например, в отдельном потоке или процессе)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Мок-объекты для SessionManager и TankPool для автономного тестирования
    class MockSessionManager:
        """Мок-класс для SessionManager."""
        def get_session_by_player_id(self, player_id):
            if player_id == "player123":
                mock_session = type('MockSession', (), {})() # Создаем простой мок-объект
                mock_session.session_id = "session789"
                mock_session.players = {"player123": {"tank_id": "tankABC"}}
                return mock_session
            return None

    class MockTank:
        """Мок-класс для Tank."""
        def __init__(self, tank_id):
            self.tank_id = tank_id
        def shoot(self):
            logger.info(f"МокТанк {self.tank_id} стреляет.")
            # Имитация отправки сообщения Kafka, как в реальном классе Tank
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, {
                "event_type": "tank_shot", "tank_id": self.tank_id, "timestamp": time.time()
            })
        def move(self, new_position):
            logger.info(f"МокТанк {self.tank_id} движется в {new_position}.")
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, { # Или KAFKA_DEFAULT_TOPIC_TANK_COORDINATES
                "event_type": "tank_moved", "tank_id": self.tank_id, 
                "position": new_position, "timestamp": time.time()
            })


    class MockTankPool:
        """Мок-класс для TankPool."""
        def get_tank(self, tank_id):
            if tank_id == "tankABC":
                return MockTank(tank_id)
            return None

    # Убедитесь, что KAFKA_BOOTSTRAP_SERVERS установлена, чтобы мок-клиент Kafka попытался подключиться
    # os.environ['KAFKA_BOOTSTRAP_SERVERS'] = 'localhost:9092' # Установите, если не установлено извне
    # os.environ['RABBITMQ_HOST'] = 'localhost' # Установите, если не установлено извне

    logger.info("Инициализация мок-компонентов для теста PlayerCommandConsumer...")
    session_manager_mock = MockSessionManager()
    tank_pool_mock = MockTankPool()

    consumer = PlayerCommandConsumer(session_manager=session_manager_mock, tank_pool=tank_pool_mock)
    try:
        logger.info("Запуск PlayerCommandConsumer для тестирования...")
        consumer.start_consuming()
    except Exception as e:
        logger.error(f"Не удалось запустить потребителя для тестирования: {e}", exc_info=True)
    finally:
        logger.info("Очистка теста PlayerCommandConsumer.")
        consumer.stop_consuming()

# Добавлен класс MatchmakingEventConsumer ниже

class MatchmakingEventConsumer:
    """
    Потребитель событий матчмейкинга из RabbitMQ.

    Отвечает за получение событий, таких как 'new_match_created', и
    взаимодействие с SessionManager для создания новых игровых сессий.
    """
    def __init__(self, session_manager: SessionManager):
        """
        Инициализирует потребителя событий матчмейкинга.

        Args:
            session_manager (SessionManager): Менеджер игровых сессий.
        """
        self.session_manager = session_manager
        self.rabbitmq_channel = None
        self.connection = None
        self.rabbitmq_host = os.environ.get('RABBITMQ_HOST', 'localhost')
        self.matchmaking_events_queue = RABBITMQ_QUEUE_MATCHMAKING_EVENTS
        self.rabbitmq_user = os.environ.get('RABBITMQ_USER', 'user')
        self.rabbitmq_password = os.environ.get('RABBITMQ_PASSWORD', 'password')

        self._connect_and_declare()

    def _connect_and_declare(self):
        """
        Устанавливает соединение с RabbitMQ и объявляет очередь событий матчмейкинга.
        """
        logger.info(f"MatchmakingEventConsumer: Попытка подключения к RabbitMQ по адресу {self.rabbitmq_host}...")
        try:
            credentials = pika.PlainCredentials(username=self.rabbitmq_user, password=self.rabbitmq_password)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbitmq_host,
                    credentials=credentials,
                    heartbeat=600, 
                    blocked_connection_timeout=300
                )
            )
            self.rabbitmq_channel = self.connection.channel()
            self.rabbitmq_channel.queue_declare(queue=self.matchmaking_events_queue, durable=True)
            self.rabbitmq_channel.basic_qos(prefetch_count=1) # Обрабатывать по одному событию
            logger.info(f"MatchmakingEventConsumer: Успешное подключение и объявление очереди '{self.matchmaking_events_queue}'.")
        except AMQPConnectionError as e:
            logger.error(f"MatchmakingEventConsumer: Не удалось подключиться к RabbitMQ: {e}. Повторная попытка через 5 секунд...")
            time.sleep(5)
            self._connect_and_declare()
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: Произошла непредвиденная ошибка во время настройки RabbitMQ: {e}", exc_info=True)

    def _callback(self, ch, method, properties, body):
        """
        Callback-функция для обработки входящих событий матчмейкинга.
        """
        try:
            logger.info(f"MatchmakingEventConsumer: Получено событие матчмейкинга через RabbitMQ: {body.decode()}")
            message_data = json.loads(body.decode())
            
            event_type = message_data.get("event_type")
            match_details = message_data.get("match_details", {}) # Детали матча

            if event_type == "new_match_created":
                # Метод SessionManager.create_session() уже отправляет сообщение в Kafka.
                session = self.session_manager.create_session() # Создаем новую сессию
                # Текущий GameSession не хранит map_id или детальное имя комнаты из матчмейкинга.
                # Это может быть улучшением для GameSession и SessionManager.
                logger.info(f"MatchmakingEventConsumer: Новая игровая сессия {session.session_id} создана из события матчмейкинга. Детали: {match_details}")
                # Если необходимо связать конкретных игроков или дополнительно настроить комнату, эта логика будет здесь.
            else:
                logger.warning(f"MatchmakingEventConsumer: Неизвестный event_type '{event_type}' в сообщении матчмейкинга. Игнорируется.")

            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем сообщение

        except json.JSONDecodeError as e:
            logger.error(f"MatchmakingEventConsumer: Не удалось декодировать JSON из сообщения матчмейкинга: {body.decode()}. Ошибка: {e}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            logger.exception(f"MatchmakingEventConsumer: Непредвиденная ошибка при обработке сообщения матчмейкинга: {body.decode()}")
            ch.basic_ack(delivery_tag=method.delivery_tag) # Подтверждаем, чтобы избежать циклов повторной обработки при ошибках

    def start_consuming(self):
        """
        Начинает потребление событий матчмейкинга.
        """
        if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
            logger.warning("MatchmakingEventConsumer: Канал RabbitMQ не открыт. Попытка переподключения...")
            self._connect_and_declare()
            if not self.rabbitmq_channel or self.rabbitmq_channel.is_closed:
                logger.error("MatchmakingEventConsumer: Не удалось переподключить канал RabbitMQ. Потребитель не может запуститься.")
                return

        logger.info(f"MatchmakingEventConsumer: Начало потребления сообщений из '{self.matchmaking_events_queue}'...")
        self.rabbitmq_channel.basic_consume(
            queue=self.matchmaking_events_queue,
            on_message_callback=self._callback
        )
        try:
            self.rabbitmq_channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("MatchmakingEventConsumer: Потребитель остановлен через KeyboardInterrupt.")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"MatchmakingEventConsumer: Ошибка потребителя: {e}. Попытка перезапуска потребления...", exc_info=True)
            self.stop_consuming()
            time.sleep(5)
            self.start_consuming()

    def stop_consuming(self):
        """
        Останавливает потребление событий и закрывает соединение.
        """
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            logger.info("MatchmakingEventConsumer: Остановка потребителя RabbitMQ...")
            try:
                self.rabbitmq_channel.stop_consuming()
            except Exception as e:
                 logger.error(f"MatchmakingEventConsumer: Ошибка при остановке потребления: {e}", exc_info=True)
            logger.info("MatchmakingEventConsumer: Потребитель RabbitMQ остановлен.")
        if self.connection and self.connection.is_open:
            logger.info("MatchmakingEventConsumer: Закрытие соединения с RabbitMQ...")
            try:
                self.connection.close()
            except Exception as e:
                logger.error(f"MatchmakingEventConsumer: Ошибка при закрытии соединения: {e}", exc_info=True)
            logger.info("MatchmakingEventConsumer: Соединение с RabbitMQ закрыто.")
