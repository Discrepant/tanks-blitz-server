# game_server/tank.py

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
        print(f"Tank {self.tank_id} moved to {self.position}")

    def shoot(self):
        # Логика выстрела
        print(f"Tank {self.tank_id} shoots!")
        pass

    def take_damage(self, damage):
        self.health -= damage
        if self.health <= 0:
            self.health = 0
            print(f"Tank {self.tank_id} destroyed!")
        else:
            print(f"Tank {self.tank_id} took {damage} damage, health is now {self.health}")

    def reset(self, initial_position=(0,0), health=100):
        self.position = initial_position
        self.health = health
        self.is_active = False
        self.last_update_time = 0
        print(f"Tank {self.tank_id} has been reset.")

    def get_state(self):
        """Возвращает текущее состояние танка для отправки клиентам."""
        return {
            'id': self.tank_id,
            'position': self.position,
            'health': self.health
        }
