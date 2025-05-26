# game_server/tank.py
import time # For timestamps
from core.message_broker_clients import send_kafka_message, KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, KAFKA_DEFAULT_TOPIC_GAME_EVENTS
import logging # Add logging

logger = logging.getLogger(__name__) # Initialize logger

class Tank:
    def __init__(self, tank_id, initial_position=(0, 0), health=100):
        self.tank_id = tank_id
        self.position = initial_position
        self.health = health
        self.is_active = False # Активен ли танк в данный момент (взят из пула)
        self.last_update_time = 0 # Для дельта-обновлений

    def move(self, new_position):
        self.position = new_position
        # Здесь может быть более сложная логика движения, валидация и т.д.
        logger.info(f"Tank {self.tank_id} moved to {self.position}")
        kafka_message = {
            "event_type": "tank_moved",
            "tank_id": self.tank_id,
            "position": self.position,
            "timestamp": time.time()
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_TANK_COORDINATES, kafka_message)

    def shoot(self):
        # Логика выстрела
        logger.info(f"Tank {self.tank_id} shoots from {self.position}!")
        kafka_message = {
            "event_type": "tank_shot",
            "tank_id": self.tank_id,
            "position_at_shot": self.position,
            "timestamp": time.time()
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_message)
        pass

    def take_damage(self, damage):
        self.health -= damage
        health_before_clamp = self.health + damage # Health before this damage event
        
        kafka_damage_message = {
            "event_type": "tank_took_damage",
            "tank_id": self.tank_id,
            "damage_taken": damage,
            "current_health": max(0, self.health), # Log health clamped at 0
            "health_before_damage": health_before_clamp,
            "timestamp": time.time()
        }
        send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_damage_message)

        if self.health <= 0:
            self.health = 0
            logger.info(f"Tank {self.tank_id} destroyed!")
            kafka_destroyed_message = {
                "event_type": "tank_destroyed",
                "tank_id": self.tank_id,
                "timestamp": time.time()
            }
            send_kafka_message(KAFKA_DEFAULT_TOPIC_GAME_EVENTS, kafka_destroyed_message)
        else:
            logger.info(f"Tank {self.tank_id} took {damage} damage, health is now {self.health}")

    def reset(self, initial_position=(0,0), health=100):
        self.position = initial_position
        self.health = health
        self.is_active = False
        self.last_update_time = 0
        logger.info(f"Tank {self.tank_id} has been reset.")

    def get_state(self):
        """Возвращает текущее состояние танка для отправки клиентам."""
        return {
            'id': self.tank_id,
            'position': self.position,
            'health': self.health
        }
