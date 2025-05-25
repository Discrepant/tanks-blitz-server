# game_server/tank_pool.py
from .tank import Tank # Используем .tank, так как Tank в отдельном файле

class TankPool:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TankPool, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, pool_size=100): # Пул на 100 танков для примера
        if not hasattr(self, 'initialized'): # Гарантируем, что инициализация произойдет один раз
            self.pool = [Tank(tank_id=f"tank_{i}") for i in range(pool_size)]
            self.in_use_tanks = {} # Словарь для отслеживания используемых танков {tank_id: tank_object}
            self.initialized = True
            print(f"Tank Pool initialized with {pool_size} tanks.")

    def acquire_tank(self):
        """Получить свободный танк из пула."""
        for tank in self.pool:
            if not tank.is_active:
                tank.is_active = True
                self.in_use_tanks[tank.tank_id] = tank
                print(f"Tank {tank.tank_id} acquired from pool.")
                return tank
        print("No free tanks in the pool.")
        return None # Или выбросить исключение, если нет свободных танков

    def release_tank(self, tank_id):
        """Вернуть танк в пул."""
        tank = self.in_use_tanks.pop(tank_id, None)
        if tank:
            tank.reset() # Сброс состояния танка
            # tank.is_active = False # reset() уже это делает
            print(f"Tank {tank.tank_id} released back to pool.")
        else:
            print(f"Warning: Attempted to release a tank_id ({tank_id}) not in use or not existing.")

    def get_tank(self, tank_id):
        """Получить объект танка по ID, если он используется."""
        return self.in_use_tanks.get(tank_id)

# Пример использования (для тестирования)
if __name__ == '__main__':
    pool1 = TankPool(pool_size=5)
    pool2 = TankPool() # Это будет тот же самый экземпляр

    print(f"Pool1 is Pool2: {pool1 is pool2}")

    t1 = pool1.acquire_tank()
    t2 = pool1.acquire_tank()

    if t1:
        t1.move((10, 20))
        t1.shoot()

    if t2:
        pool1.release_tank(t2.tank_id)
    
    t3 = pool1.acquire_tank() # Должен быть t2, если он был сброшен и возвращен
    print(f"Acquired t3: {t3.tank_id if t3 else 'None'}")
