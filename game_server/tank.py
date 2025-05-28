# game_server/tank.py
# Этот модуль определяет класс Tank, представляющий игровой танк
# с его свойствами и методами.
import time # Для временных меток событий
from core.message_broker_clients import send_kafka_message, KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, KAFKA_DEFAULT_TOPIC_GAME_EVENTS
import logging # Добавляем логирование

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

class Tank:
    """
    Представляет игровой танк.

    Содержит информацию о ID танка, его позиции, здоровье, статусе активности
    и времени последнего обновления. Предоставляет методы для движения,
    стрельбы, получения урона, сброса состояния и получения текущего состояния.
    Взаимодействует с Kafka для отправки событий.

    Атрибуты:
        tank_id (any): Уникальный идентификатор танка.
        position (tuple): Текущие координаты танка (например, (x, y)).
        health (int): Текущий уровень здоровья танка.
        is_active (bool): Флаг, указывающий, активен ли танк в данный момент (взят из пула).
        last_update_time (float): Время последнего обновления состояния танка (для дельта-обновлений).
    """
    def __init__(self, tank_id, initial_position=(0, 0), health=100):
        """
        Инициализирует объект танка.

        Args:
            tank_id (any): Уникальный ID для этого танка.
            initial_position (tuple, optional): Начальная позиция танка. По умолчанию (0, 0).
            health (int, optional): Начальное количество здоровья. По умолчанию 100.
        """
        self.tank_id = tank_id
        self.position = initial_position
        self.health = health
        self.is_active = False # Изначально танк не активен, пока не взят из пула
        self.last_update_time = 0 # Время последнего обновления (полезно для дельта-сжатия или интерполяции)
        logger.info(f"Танк {self.tank_id} создан с позицией {self.position} и здоровьем {self.health}.")

    def move(self, new_position):
        """
        Перемещает танк в новую позицию.

        Обновляет позицию танка и отправляет событие 'tank_moved' в Kafka.

        Args:
            new_position (tuple): Новые координаты (x, y) для танка.
        """
        self.position = new_position
        # Здесь может быть более сложная логика движения, валидация перемещения,
        # проверка столкновений и т.д.
        logger.info(f"Танк {self.tank_id} перемещен в {self.position}")
        # Отправка сообщения в Kafka о движении танка
        kafka_message = {
            "event_type": "tank_moved", # Тип события
            "tank_id": self.tank_id,    # ID танка
            "position": self.position,  # Новая позиция
            "timestamp": time.time()    # Временная метка события
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, kafka_message)

    def shoot(self):
        """
        Выполняет выстрел из танка.

        Логирует действие выстрела и отправляет событие 'tank_shot' в Kafka.
        Конкретная логика попадания, урона и т.д. здесь не реализована.
        """
        # Логика выстрела: создание снаряда, проверка попадания и т.д.
        logger.info(f"Танк {self.tank_id} стреляет из позиции {self.position}!")
        # Отправка сообщения в Kafka о выстреле
        kafka_message = {
            "event_type": "tank_shot",
            "tank_id": self.tank_id,
            "position_at_shot": self.position, # Позиция танка в момент выстрела
            "timestamp": time.time()
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_message)
        # pass здесь означает, что дальнейшая логика выстрела (например, создание объекта снаряда)
        # может быть добавлена позже или обрабатывается другими системами.
        pass

    def take_damage(self, damage):
        """
        Уменьшает здоровье танка на указанное количество урона.

        Отправляет события 'tank_took_damage' и, если здоровье <= 0, 'tank_destroyed' в Kafka.
        Здоровье не может быть меньше 0.

        Args:
            damage (int): Количество полученного урона.
        """
        health_before_damage = self.health # Запоминаем здоровье до получения урона для лога
        self.health -= damage
        
        # Отправляем сообщение о получении урона
        kafka_damage_message = {
            "event_type": "tank_took_damage",
            "tank_id": self.tank_id,
            "damage_taken": damage,
            "current_health": max(0, self.health), # Логируем здоровье, ограниченное снизу нулем
            "health_before_damage": health_before_damage,
            "timestamp": time.time()
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_damage_message)

        if self.health <= 0:
            self.health = 0 # Здоровье не может быть отрицательным
            logger.info(f"Танк {self.tank_id} уничтожен!")
            # Отправляем сообщение об уничтожении танка
            kafka_destroyed_message = {
                "event_type": "tank_destroyed",
                "tank_id": self.tank_id,
                "timestamp": time.time()
            }
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_destroyed_message)
            # Здесь может быть логика деактивации танка, удаления из игры и т.д.
        else:
            logger.info(f"Танк {self.tank_id} получил {damage} урона, текущее здоровье: {self.health}")

    def reset(self, initial_position=(0,0), health=100):
        """
        Сбрасывает состояние танка к начальным значениям.

        Используется при возвращении танка в пул объектов.

        Args:
            initial_position (tuple, optional): Начальная позиция для сброса. По умолчанию (0,0).
            health (int, optional): Начальное здоровье для сброса. По умолчанию 100.
        """
        self.position = initial_position
        self.health = health
        self.is_active = False # Помечаем как неактивный
        self.last_update_time = 0 # Сбрасываем время обновления
        logger.info(f"Танк {self.tank_id} был сброшен в начальное состояние.")

    def get_state(self):
        """
        Возвращает текущее состояние танка.

        Это состояние может использоваться для отправки клиентам или для логирования.

        Returns:
            dict: Словарь с состоянием танка (ID, позиция, здоровье).
        """
        return {
            'id': self.tank_id,
            'position': self.position,
            'health': self.health
            # Можно добавить и другие параметры, например, self.is_active, если это нужно клиенту
        }
