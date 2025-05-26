# tests/load/locustfile_game.py
from locust import User, task, between
import socket
import time
import json
import random
import uuid

# Простой UDP клиент для Locust
class UDPClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP не требует "connect" перед sendto, но можно установить таймаут
        self._socket.settimeout(2.0) # Таймаут для recv, например 2 секунды

    def send(self, data):
        self._socket.sendto(data.encode(), (self.host, self.port))

    def recv(self, length=1024):
        try:
            data, addr = self._socket.recvfrom(length)
            return data.decode()
        except socket.timeout:
            # print("UDP recv timed out")
            return None
        except Exception as e:
            # print(f"UDP recv error: {e}")
            return None # Или можно выбросить исключение, чтобы Locust его поймал

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None

class GameUser(User):
    wait_time = between(0.5, 2) # Игроки действуют чаще
    host = "localhost"  # Хост игрового сервера
    port = 9999         # Порт игрового сервера

    def on_start(self):
        self.client = UDPClient(self.host, self.port)
        self.player_id = str(uuid.uuid4()) # Уникальный ID для этого locust-пользователя
        self.session_id = None
        self.tank_id = None
        self.joined_game = False
        
        # Попытка присоединиться к игре при старте
        self.join_game()

    def join_game(self):
        if self.joined_game: return

        request_data = {
            "action": "join_game",
            "player_id": self.player_id
        }
        start_time = time.time()
        try:
            self.client.send(json.dumps(request_data))
            response_str = self.client.recv()
            end_time = time.time()

            if response_str:
                response = json.loads(response_str)
                if response.get("status") == "joined":
                    self.session_id = response.get("session_id")
                    self.tank_id = response.get("tank_id")
                    self.joined_game = True
                    self.environment.events.request.fire(
                        request_type="UDP_GAME", name="join_game_success", response_time=(end_time - start_time) * 1000,
                        response_length=len(response_str), context=self.environment, exception=None
                    )
                else:
                    raise Exception(f"Join failed: {response.get('reason', 'unknown')}")
            else:
                raise Exception("No response on join_game")
        except Exception as e:
            end_time = time.time()
            self.environment.events.request.fire(
                request_type="UDP_GAME", name="join_game_fail", response_time=(end_time - start_time) * 1000,
                response_length=0, context=self.environment, exception=e
            )

    @task(1) # Задача с большим весом - присоединение, если не в игре
    def ensure_joined(self):
        if not self.joined_game:
            self.join_game()

    @task(5) # Остальные задачи выполняются чаще, если игрок в игре
    def perform_ingame_action(self):
        if not self.joined_game or not self.tank_id:
            # print(f"Player {self.player_id} not in game, skipping ingame action.")
            return

        actions = ["move", "shoot"] # "leave_game" можно добавить, но тогда нужно будет снова join
        chosen_action = random.choice(actions)
        
        request_data = {"player_id": self.player_id} # tank_id не нужен в запросе, сервер знает его по player_id

        if chosen_action == "move":
            request_data["action"] = "move"
            request_data["position"] = [random.randint(0, 100), random.randint(0, 100)]
        elif chosen_action == "shoot":
            request_data["action"] = "shoot"
        
        action_name = f"action_{chosen_action}"
        start_time = time.time()
        try:
            self.client.send(json.dumps(request_data))
            # Для UDP часто не ждут ответа на каждое действие, кроме критичных.
            # Здесь мы можем либо ждать и парсить game_update, либо просто считать отправку успешной.
            # Для простоты, не будем ждать ответа на move/shoot, но в реальном тесте это может быть нужно.
            # response_str = self.client.recv() # Если ожидается ответ
            # if response_str:
            #    # ... обработка ответа ...
            #    pass
            
            end_time = time.time()
            self.environment.events.request.fire(
                request_type="UDP_GAME", name=action_name, response_time=(end_time - start_time) * 1000,
                response_length=len(json.dumps(request_data)), context=self.environment, exception=None # Предполагаем успех, если нет ответа
            )
        except Exception as e:
            end_time = time.time()
            self.environment.events.request.fire(
                request_type="UDP_GAME", name=action_name, response_time=(end_time - start_time) * 1000,
                response_length=0, context=self.environment, exception=e
            )

    def on_stop(self):
        if self.joined_game and self.client:
            request_data = {
                "action": "leave_game",
                "player_id": self.player_id
            }
            try:
                self.client.send(json.dumps(request_data))
                # Можно подождать ответ, если он есть
                # self.client.recv() 
            except Exception as e:
                print(f"Error sending leave_game for {self.player_id}: {e}")
        
        if self.client:
            self.client.close()
        print(f"GameUser {self.player_id} stopped.")

# Для запуска: locust -f tests/load/locustfile_game.py GameUser
# locust -f tests/load/locustfile_game.py GameUser --headless -u 50 -r 10 --run-time 1m 
# (50 пользователей, 10 в секунду, 1 минута)
