# tests/load/locustfile_game.py
# Этот файл содержит сценарий нагрузочного тестирования для игрового UDP-сервера
# с использованием Locust. Имитирует пользователей, которые присоединяются к игре,
# выполняют игровые действия (движение, стрельба) и покидают игру.

from locust import User, task, between # Основные классы Locust
import socket # Для UDP-соединений
import time # Для временных меток и задержек
import json # Для сериализации/десериализации сообщений
import random # Для случайного выбора действий и координат
import uuid # Для генерации уникальных ID игроков
import logging # Для логирования

# Настройка логирования для locustfile
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Простой UDP-клиент для Locust.
# В отличие от TCP, UDP является протоколом без установления соединения.
class UDPClient:
    """
    Простой UDP-клиент для отправки и получения датаграмм.
    Используется GameUser для взаимодействия с UDP-сервером игры.
    """
    def __init__(self, host: str, port: int):
        """
        Инициализирует UDP-клиент.

        Args:
            host (str): Хост сервера.
            port (int): Порт сервера.
        """
        self.host = host
        self.port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # Создаем UDP-сокет
        # UDP не требует вызова "connect" перед sendto.
        # Таймаут устанавливается для операции recvfrom, чтобы она не блокировалась вечно.
        self._socket.settimeout(2.0) # Таймаут для recvfrom, например, 2 секунды

    def send(self, data_str: str):
        """
        Отправляет строковые данные на сервер по UDP.
        Данные кодируются в UTF-8.

        Args:
            data_str (str): Строка данных для отправки.
        """
        try:
            self._socket.sendto(data_str.encode('utf-8'), (self.host, self.port))
            logger.debug(f"UDPClient: Отправлено на {self.host}:{self.port}: {data_str}")
        except Exception as e:
            logger.error(f"UDPClient: Ошибка при отправке данных - {e}")
            # Для UDP ошибки отправки менее вероятны на этом этапе, чем при получении,
            # но обработка не помешает.
            raise

    def recv(self, length: int = 1024) -> str | None:
        """
        Получает данные от сервера по UDP.

        Args:
            length (int, optional): Максимальное количество байт для получения.
                                    По умолчанию 1024.

        Returns:
            str | None: Декодированная строка ответа или None в случае таймаута или ошибки.
                        В реальном тесте можно рассмотреть выброс исключения,
                        чтобы Locust зарегистрировал ошибку.
        """
        try:
            data_bytes, server_addr = self._socket.recvfrom(length) # Получаем данные и адрес отправителя
            response_str = data_bytes.decode('utf-8')
            logger.debug(f"UDPClient: Получено от {server_addr}: {response_str}")
            return response_str
        except socket.timeout:
            logger.warning("UDPClient: Таймаут при получении данных (recvfrom).")
            return None # Возвращаем None при таймауте
        except Exception as e:
            logger.error(f"UDPClient: Ошибка при получении данных (recvfrom) - {e}")
            return None # Или можно выбросить исключение, чтобы Locust его поймал и зарегистрировал

    def close(self):
        """Закрывает UDP-сокет, если он открыт."""
        if self._socket:
            try:
                self._socket.close()
                logger.debug("UDPClient: Сокет закрыт.")
            except Exception as e:
                logger.error(f"UDPClient: Ошибка при закрытии сокета - {e}")
            finally:
                self._socket = None

class GameUser(User):
    """
    Класс пользователя Locust для тестирования игрового UDP-сервера.
    Имитирует поведение игрока: присоединение к игре, выполнение действий, выход.
    """
    wait_time = between(0.5, 2) # Игроки действуют чаще, чем пользователи в AuthUser
    host = "localhost"  # Хост игрового сервера (можно переопределить из командной строки)
    port = 9999         # UDP-порт игрового сервера

    def on_start(self):
        """
        Вызывается при старте каждого виртуального пользователя Locust.
        Инициализирует UDP-клиент, генерирует ID игрока и пытается присоединиться к игре.
        """
        self.client = UDPClient(self.host, self.port)
        self.player_id = str(uuid.uuid4()) # Генерируем уникальный ID для этого пользователя Locust
        self.session_id = None # ID сессии, к которой присоединился игрок
        self.tank_id = None    # ID танка, полученного игроком
        self.joined_game = False # Флаг, указывающий, находится ли игрок в игре
        
        logger.info(f"GameUser {self.player_id}: Старт. Попытка присоединиться к игре...")
        # Попытка присоединиться к игре сразу при старте пользователя
        self.join_game()

    def join_game(self):
        """
        Отправляет запрос 'join_game' на сервер и обрабатывает ответ.
        Обновляет состояние пользователя (session_id, tank_id, joined_game).
        Регистрирует результат в статистике Locust.
        """
        if self.joined_game: return # Если уже в игре, ничего не делаем

        request_data = {
            "action": "join_game",
            "player_id": self.player_id
        }
        start_time = time.time() # Время начала запроса
        try:
            self.client.send(json.dumps(request_data)) # Отправляем JSON-строку
            response_str = self.client.recv() # Получаем ответ
            end_time = time.time() # Время окончания запроса

            if response_str:
                response_json = json.loads(response_str) # Парсим JSON-ответ
                if response_json.get("status") == "joined":
                    self.session_id = response_json.get("session_id")
                    self.tank_id = response_json.get("tank_id")
                    self.joined_game = True
                    logger.info(f"GameUser {self.player_id}: Успешно присоединился к сессии {self.session_id} с танком {self.tank_id}.")
                    # Регистрируем успешное присоединение в Locust
                    self.environment.events.request.fire(
                        request_type="UDP_GAME", name="join_game_success", response_time=int((end_time - start_time) * 1000),
                        response_length=len(response_str.encode('utf-8')), context=self.environment, exception=None
                    )
                else: # Если статус не "joined"
                    logger.warning(f"GameUser {self.player_id}: Не удалось присоединиться - {response_json.get('reason', 'неизвестная причина')}.")
                    raise Exception(f"Присоединение не удалось: {response_json.get('reason', 'неизвестная причина')}")
            else: # Если ответ не получен (например, таймаут)
                logger.warning(f"GameUser {self.player_id}: Нет ответа от сервера при попытке присоединения.")
                raise Exception("Нет ответа от сервера на запрос join_game") # "No response from server on join_game request"
        except Exception as e: # Обработка любых исключений (включая JSONDecodeError, таймауты и т.д.)
            end_time = time.time()
            logger.error(f"GameUser {self.player_id}: Ошибка при присоединении к игре - {e}")
            # Регистрируем ошибку присоединения в Locust
            self.environment.events.request.fire(
                request_type="UDP_GAME", name="join_game_failure", response_time=int((end_time - start_time) * 1000),
                response_length=0, context=self.environment, exception=e
            )

    @task(1) # Задача с большим весом: убедиться, что игрок в игре.
    def ensure_joined(self):
        """
        Задача Locust: если пользователь еще не в игре, пытается присоединиться.
        Это гарантирует, что другие задачи будут выполняться только после успешного входа.
        """
        if not self.joined_game:
            logger.debug(f"GameUser {self.player_id}: Не в игре, попытка ensure_joined.")
            self.join_game()

    @task(5) # Остальные игровые действия выполняются чаще.
    def perform_ingame_action(self):
        """
        Задача Locust: выполнение случайного игрового действия (движение или стрельба).
        Выполняется только если игрок успешно присоединился к игре.
        """
        if not self.joined_game or not self.tank_id:
            # logger.debug(f"GameUser {self.player_id}: Не в игре или нет танка, пропускаем игровое действие.")
            return # Если не в игре или нет танка, пропускаем действие

        actions = ["move", "shoot"] # Возможные действия
        # "leave_game" можно добавить, но тогда нужно будет снова выполнять join_game
        chosen_action = random.choice(actions) # Выбираем случайное действие
        
        request_data = {"player_id": self.player_id} # ID игрока обязателен
        # ID танка не нужен в запросе, так как сервер связывает player_id с tank_id при join_game.

        if chosen_action == "move":
            request_data["action"] = "move"
            # Генерируем случайные координаты для движения
            request_data["position"] = [random.randint(0, 100), random.randint(0, 100)]
        elif chosen_action == "shoot":
            request_data["action"] = "shoot"
        
        action_name_for_locust = f"action_{chosen_action}" # Имя для статистики Locust
        start_time = time.time()
        try:
            self.client.send(json.dumps(request_data))
            # Для UDP часто не ждут ответа на каждое действие, кроме критичных (как join_game).
            # Здесь мы можем либо ждать и парсить широковещательное обновление состояния игры (game_update),
            # либо просто считать отправку команды успешной и не ждать ответа.
            # Для простоты, не будем ждать явного ответа на команды move/shoot,
            # но в реальном нагрузочном тесте это может потребоваться для проверки корректности.
            # response_str = self.client.recv() # Если бы мы ожидали ответ
            # if response_str:
            #    # ... обработка ответа ...
            #    pass
            
            end_time = time.time()
            # Регистрируем успешную отправку команды в Locust.
            # Длина ответа здесь условна, так как мы не ждем специфического ответа.
            self.environment.events.request.fire(
                request_type="UDP_GAME", name=action_name_for_locust, response_time=int((end_time - start_time) * 1000),
                response_length=len(json.dumps(request_data).encode('utf-8')), # Длина отправленного запроса
                context=self.environment, exception=None # Предполагаем успех, если нет исключения при отправке
            )
            logger.debug(f"GameUser {self.player_id}: Выполнено действие '{chosen_action}'.")
        except Exception as e: # Обработка ошибок при отправке
            end_time = time.time()
            logger.error(f"GameUser {self.player_id}: Ошибка при выполнении действия '{chosen_action}' - {e}")
            self.environment.events.request.fire(
                request_type="UDP_GAME", name=action_name_for_locust + "_failure", 
                response_time=int((end_time - start_time) * 1000),
                response_length=0, context=self.environment, exception=e
            )

    def on_stop(self):
        """
        Вызывается при остановке виртуального пользователя Locust.
        Отправляет команду 'leave_game' и закрывает UDP-клиент.
        """
        logger.info(f"GameUser {self.player_id}: Остановка.")
        if self.joined_game and self.client: # Если пользователь был в игре
            request_data = {
                "action": "leave_game",
                "player_id": self.player_id
            }
            try:
                self.client.send(json.dumps(request_data))
                # Можно подождать ответ от сервера на leave_game, если он предусмотрен.
                # response_str = self.client.recv()
                # if response_str: logger.info(f"GameUser {self.player_id}: Ответ на leave_game: {response_str}")
                logger.info(f"GameUser {self.player_id}: Отправлена команда leave_game.")
            except Exception as e:
                logger.error(f"GameUser {self.player_id}: Ошибка при отправке команды leave_game - {e}")
        
        if self.client: # Закрываем клиент в любом случае
            self.client.close()
        logger.info(f"GameUser {self.player_id} остановлен, клиент закрыт.")

# Инструкции по запуску Locust (если запускать из командной строки):
# 1. Убедитесь, что игровой UDP-сервер запущен.
# 2. Перейдите в директорию, где находится этот locustfile.
# 3. Команда для запуска с веб-интерфейсом:
#    locust -f tests/load/locustfile_game.py
#    Затем откройте http://localhost:8089 в браузере.
#
# 4. Команда для запуска без веб-интерфейса (headless):
#    locust -f tests/load/locustfile_game.py GameUser --headless -u 50 -r 10 --run-time 1m
#    Описание параметров:
#    -u 50: количество одновременных пользователей
#    -r 10: количество пользователей, запускаемых в секунду (spawn rate)
#    --run-time 1m: продолжительность теста (1 минута)
#
# Примечание: Этот locustfile использует JSON для обмена данными с сервером,
# как и было реализовано в GameUDPProtocol.
