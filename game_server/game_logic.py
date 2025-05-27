import asyncio
import logging # Added import
from .auth_client import AuthClient # Клиент для сервера аутентификации
from .models import Player # Модель игрока

logger = logging.getLogger(__name__) # Added logger

class GameRoom:
    def __init__(self, auth_client: AuthClient):
        self.players = {} # Словарь для хранения активных игроков {username: Player}
        self.auth_client = auth_client
        self.next_player_id = 1
        self.match_history = [] # Здесь можно хранить историю матчей

    async def authenticate_player(self, username, password):
        """
        Аутентифицирует игрока через внешний сервис аутентификации.
        Возвращает (bool, str, str|None): (успех, сообщение, session_token)
        """
        authenticated, message, session_token = await self.auth_client.login_user(username, password)
        return authenticated, message, session_token

    async def add_player(self, player: Player):
        logger.debug(f"GameRoom.add_player: About to check 'in'. self.players type: {type(self.players)}, value: {self.players!r}")
        logger.debug(f"GameRoom.add_player: About to check 'in'. player.name type: {type(player.name)}, value: {player.name!r}")
        if player.name in self.players:
            # Обработка случая, если игрок уже в комнате (например, переподключение)
            # Пока просто не добавляем, если уже существует с таким именем
            await player.send_message(f"SERVER: Игрок с именем {player.name} уже в комнате.")
            print(f"Попытка добавить существующего игрока: {player.name}")
            # Возможно, стоит закрыть старое соединение или обновить writer
            return

        self.players[player.name] = player
        print(f"Игрок {player.name} (ID: {player.id}) добавлен в игровую комнату. Всего игроков: {len(self.players)}")
        await player.send_message("SERVER: Добро пожаловать в игровую комнату!")
        await self.broadcast_message(f"SERVER: Игрок {player.name} присоединился к комнате.", exclude_player=player)

    async def remove_player(self, player: Player):
        if player.name in self.players:
            del self.players[player.name]
            print(f"Игрок {player.name} удален из игровой комнаты. Осталось игроков: {len(self.players)}")
            await self.broadcast_message(f"SERVER: Игрок {player.name} покинул комнату.")
        if player.writer and not player.writer.is_closing():
            try:
                player.writer.close()
                await player.writer.wait_closed()
            except Exception as e:
                print(f"Ошибка при закрытии writer для {player.name}: {e}")


    async def broadcast_message(self, message: str, exclude_player: Player = None):
        disconnected_players = []
        for p_name, p_obj in self.players.items():
            if p_obj != exclude_player:
                try:
                    await p_obj.send_message(message)
                except ConnectionResetError:
                    print(f"Ошибка отправки игроку {p_name}: соединение сброшено. Планируем удаление.")
                    disconnected_players.append(p_obj) # Собираем игроков для удаления
                except Exception as e:
                    print(f"Ошибка при трансляции сообщения игроку {p_name}: {e}")
                    # Можно добавить логику для обработки других ошибок отправки,
                    # например, пометить игрока как "проблемный"

        # Удаляем игроков, у которых соединение было сброшено
        for p_obj in disconnected_players:
            if p_obj.name in self.players: # Проверяем, не был ли уже удален
                 await self.remove_player(p_obj)


    async def handle_player_command(self, player: Player, command_message: str):
        parts = command_message.split(" ", 1)
        command = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if command == "SAY":
            await self.broadcast_message(f"{player.name}: {args}", exclude_player=None)
        elif command == "HELP":
            await player.send_message("SERVER: Доступные команды: SAY <сообщение>, PLAYERS, QUIT")
        elif command == "PLAYERS":
            player_list = ", ".join(self.players.keys())
            await player.send_message(f"SERVER: Игроки в комнате: {player_list}")
        elif command == "QUIT":
            await player.send_message("SERVER: Вы выходите из комнаты...")
            # remove_player будет вызван из tcp_handler при закрытии соединения
            if player.writer and not player.writer.is_closing():
                player.writer.close() # Инициируем закрытие соединения
        # Добавить другие игровые команды здесь
        # Например, начало игры, ходы и т.д.
        else:
            await player.send_message(f"SERVER: Неизвестная команда '{command}'. Введите HELP для списка команд.")

    # Пример методов для будущей игровой логики
    async def start_match(self, player1: Player, player2: Player):
        # Логика начала матча
        pass

    async def record_match_result(self, winner: Player, loser: Player, details: str):
        # Запись результата матча
        pass
