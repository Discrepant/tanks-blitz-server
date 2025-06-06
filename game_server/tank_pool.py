# game_server/tank_pool.py
# Этот модуль определяет класс TankPool, реализующий паттерн "Пул объектов"
# для управления экземплярами танков.
from .tank import Tank # Используем относительный импорт, так как Tank находится в том же пакете
import logging # Добавляем логирование
from .metrics import TANKS_IN_USE # Импортируем метрику

logger = logging.getLogger(__name__) # Инициализация логгера

class TankPool:
    """
    Пул объектов для управления экземплярами танков (Tank).

    Реализован как Singleton, чтобы обеспечить единый пул танков для всего сервера.
    Позволяет получать (acquire) танки из пула и возвращать (release) их обратно
    для повторного использования.

    Атрибуты:
        pool (list[Tank]): Список всех экземпляров танков, управляемых пулом.
        in_use_tanks (dict[str, Tank]): Словарь для отслеживания используемых танков,
                                        где ключ - ID танка, значение - объект Tank.
    """
    _instance = None # Экземпляр Singleton

    def __new__(cls, *args, **kwargs):
        """
        Реализация паттерна Singleton.
        *args и **kwargs передаются для возможности их использования в __init__.
        """
        if not cls._instance:
            cls._instance = super(TankPool, cls).__new__(cls)
        return cls._instance

    def __init__(self, pool_size=100):
        """
        Инициализирует пул танков.

        Создает заданное количество экземпляров Tank и добавляет их в пул.
        Инициализация происходит только один раз благодаря проверке `hasattr(self, 'initialized')`.

        Args:
            pool_size (int, optional): Начальный размер пула (количество танков).
                                       По умолчанию 100.
        """
        if not hasattr(self, 'initialized'): # Гарантируем, что инициализация произойдет один раз
            # Создаем список объектов Tank. ID танка генерируется как "tank_i".
            self.pool = [Tank(tank_id=f"tank_{i}") for i in range(pool_size)]
            # Словарь для отслеживания используемых танков: {tank_id: tank_object}
            self.in_use_tanks = {} 
            self.initialized = True
            logger.info(f"Tank pool initialized with {pool_size} tanks.")

    def acquire_tank(self):
        """
        Получает свободный танк из пула.

        Ищет в пуле неактивный танк, помечает его как активный, добавляет в
        `in_use_tanks` и возвращает.

        Returns:
            Tank | None: Свободный объект Tank, если найден, иначе None.
                         В продакшн-системе может быть предпочтительнее выбросить исключение,
                         если свободных танков нет и это критично.
        """
        for tank in self.pool:
            if not tank.is_active: # Если танк не активен (т.е. свободен)
                tank.is_active = True # Помечаем как активный
                self.in_use_tanks[tank.tank_id] = tank # Добавляем в словарь используемых
                TANKS_IN_USE.inc() # Обновляем метрику
                logger.info(f"Tank {tank.tank_id} acquired from pool. TANKS_IN_USE incremented.")
                return tank
        logger.warning("No free tanks available in the pool.")
        return None # Возвращаем None, если все танки заняты

    def release_tank(self, tank_id):
        """
        Возвращает танк с указанным ID обратно в пул.

        Удаляет танк из `in_use_tanks` и сбрасывает его состояние
        (через метод `tank.reset()`), делая его доступным для повторного использования.

        Args:
            tank_id (str): ID танка, который нужно вернуть в пул.
        """
        tank = self.in_use_tanks.pop(tank_id, None) # Удаляем танк из используемых
        if tank:
            tank.reset() # Сбрасываем состояние танка (включая is_active = False)
            TANKS_IN_USE.dec() # Обновляем метрику
            logger.info(f"Tank {tank.tank_id} released back to pool. TANKS_IN_USE decremented.")
        else:
            # Попытка вернуть танк, который не был помечен как используемый или не существует.
            logger.warning(f"Warning: Attempt to release tank with ID ({tank_id}) that is not in use or does not exist.")

    def get_tank(self, tank_id):
        """
        Получает объект используемого танка по его ID.

        Args:
            tank_id (str): ID запрашиваемого танка.

        Returns:
            Tank | None: Объект Tank, если танк с таким ID используется, иначе None.
        """
        return self.in_use_tanks.get(tank_id)

# Пример использования (для тестирования, если модуль запускается напрямую)
if __name__ == '__main__':
    # Настройка логирования для примера
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    pool1 = TankPool(pool_size=5) # Создание/получение экземпляра пула
    pool2 = TankPool() # Это должен быть тот же самый экземпляр (Singleton)

    logger.info(f"Pool1 is Pool2: {pool1 is pool2}") # Проверка Singleton

    # Берем два танка из пула
    t1 = pool1.acquire_tank()
    t2 = pool1.acquire_tank()

    if t1:
        logger.info(f"Acquired tank t1: {t1.tank_id}")
        t1.move((10, 20)) # Используем методы танка
        t1.shoot()
    else:
        logger.warning("Failed to acquire tank t1.")

    if t2:
        logger.info(f"Acquired tank t2: {t2.tank_id}")
        pool1.release_tank(t2.tank_id) # Возвращаем t2 в пул
    else:
        logger.warning("Failed to acquire tank t2.")
    
    # Пытаемся взять еще один танк. Если t2 был возвращен, t3 должен быть им.
    t3 = pool1.acquire_tank() 
    logger.info(f"Acquired tank t3: {t3.tank_id if t3 else 'None'}")

    # Проверяем состояние пула
    logger.info(f"Tanks in use: {list(pool1.in_use_tanks.keys())}")
    logger.info(f"Number of free tanks: {sum(1 for t in pool1.pool if not t.is_active)}")
