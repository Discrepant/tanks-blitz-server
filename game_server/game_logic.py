# game_server/game_logic.py
# Этот модуль содержит класс GameRoom, который управляет состоянием
# игровой комнаты, игроками в ней и обработкой их команд.
import asyncio
import logging # Добавлен импорт для логирования
from .auth_client import AuthClient # Клиент для сервера аутентификации
from .models import Player # Модель игрока (представление данных игрока)

logger = logging.getLogger(__name__) # Инициализация логгера для этого модуля

class GameRoom:
    """
    Управляет состоянием одной игровой комнаты, включая игроков,
    аутентификацию и обработку команд.

    Атрибуты:
        players (dict[str, Player]): Словарь активных игроков в комнате,
                                     где ключ - имя пользователя, значение - объект Player.
        auth_client (AuthClient): Клиент для взаимодействия с сервером аутентификации.
        next_player_id (int): Счетчик для генерации уникальных ID игроков (в текущей реализации не используется для Player.id).
        match_history (list): Список для хранения истории матчей (пока не используется).
    """
    def __init__(self, auth_client: AuthClient):
        """
        Инициализирует игровую комнату.

        Args:
            auth_client (AuthClient): Экземпляр клиента аутентификации.
        """
        self.players = {} # Словарь для хранения активных игроков {имя_пользователя: Player}
        self.auth_client = auth_client
        self.next_player_id = 1 # Используется для генерации ID, если Player.id не задан иначе
        self.match_history = [] # Здесь можно хранить историю матчей (пока не реализовано)

    async def authenticate_player(self, username, password):
        """
        Аутентифицирует игрока через внешний сервис аутентификации (AuthClient).

        Args:
            username (str): Имя пользователя для аутентификации.
            password (str): Пароль пользователя.

        Returns:
            tuple[bool, str, str|None]: Кортеж, содержащий:
                - bool: True, если аутентификация успешна, иначе False.
                - str: Сообщение от сервера аутентификации.
                - str|None: Токен сессии, если аутентификация успешна и токен предоставлен, иначе None.
        """
        authenticated, message, session_token = await self.auth_client.login_user(username, password)
        logger.info(f"Authentication attempt for '{username}': success={authenticated}, message='{message}', token='{session_token}'")
        return authenticated, message, session_token

    async def add_player(self, player: Player):
        """
        Добавляет игрока в игровую комнату.

        Если игрок с таким именем уже существует, новое подключение не добавляется,
        и отправляется сообщение существующему игроку. При успешном добавлении,
        новый игрок получает приветственное сообщение, а остальные игроки
        уведомляются о его присоединении.

        Args:
            player (Player): Объект игрока для добавления.
        """
        # Отладочные логи для проверки типов и значений перед проверкой наличия игрока
        logger.debug(f"GameRoom.add_player: Проверка 'in'. Тип self.players: {type(self.players)}, значение: {self.players!r}")
        logger.debug(f"GameRoom.add_player: Проверка 'in'. Тип player.name: {type(player.name)}, значение: {player.name!r}")
        
        if player.name in self.players:
            # Обработка случая, если игрок уже в комнате (например, попытка повторного подключения с тем же именем).
            # Текущая логика: просто не добавляем, если игрок с таким именем уже существует.
            # Отправляем сообщение об этом существующему (или новому пытающемуся подключиться) игроку.
            logger.warning(f"Attempt to add existing player: {player.name}. Sending message.")
            await player.send_message(f"SERVER: Player with name {player.name} is already in the room or an error occurred.") # Already in English
            # Возможно, стоит рассмотреть закрытие старого соединения или обновление writer для существующего игрока.
            return

        self.players[player.name] = player
        logger.info(f"Player {player.name} (ID: {player.id}) added to game room. Total players: {len(self.players)}")
        await player.send_message("SERVER: Welcome to the game room!") # Already in English
        await self.broadcast_message(f"SERVER: Player {player.name} joined the room.", exclude_player=player) # Already in English

    async def remove_player(self, player: Player):
        """
        Удаляет игрока из игровой комнаты.

        Если игрок найден, он удаляется из словаря `self.players`,
        и остальные игроки уведомляются о его выходе.
        Также производится попытка закрыть сетевое соединение игрока.

        Args:
            player (Player): Объект игрока для удаления.
        """
        if player.name in self.players:
            del self.players[player.name]
            logger.info(f"Player {player.name} removed from game room. Players remaining: {len(self.players)}")
            await self.broadcast_message(f"SERVER: Player {player.name} left the room.") # Already in English
        
        # Пытаемся корректно закрыть writer, если он существует и не закрывается
        if player.writer and not player.writer.is_closing():
            try:
                player.writer.close()
                await player.writer.wait_closed()
                logger.debug(f"Writer for player {player.name} successfully closed.")
            except Exception as e:
                logger.error(f"Error closing writer for {player.name}: {e}", exc_info=True)


    async def broadcast_message(self, message: str, exclude_player: Player = None):
        """
        Отправляет сообщение всем игрокам в комнате, за исключением указанного.

        Обрабатывает возможные ошибки соединения (ConnectionResetError) при отправке,
        собирает список "отключившихся" игроков и удаляет их из комнаты.

        Args:
            message (str): Сообщение для трансляции.
            exclude_player (Player, optional): Игрок, которому не нужно отправлять сообщение.
                                               По умолчанию None.
        """
        disconnected_players = [] # Список для игроков, у которых соединение было сброшено
        # Создаем копию items для безопасной итерации, если self.players может изменяться (хотя здесь не должно)
        for p_name, p_obj in list(self.players.items()): 
            if p_obj != exclude_player:
                try:
                    await p_obj.send_message(message)
                except ConnectionResetError:
                    logger.warning(f"Error sending to player {p_name}: connection reset. Scheduling removal.")
                    disconnected_players.append(p_obj) # Собираем игроков для последующего удаления
                except Exception as e:
                    logger.error(f"Error broadcasting message to player {p_name}: {e}", exc_info=True)
                    # Можно добавить логику для обработки других ошибок отправки,
                    # например, пометить игрока как "проблемного" или увеличить счетчик ошибок.

        # Удаляем игроков, у которых соединение было сброшено
        for p_obj in disconnected_players:
            if p_obj.name in self.players: # Проверяем, не был ли игрок уже удален (например, двойной вызов)
                 logger.info(f"Removing player {p_obj.name} due to connection reset during broadcast.")
                 await self.remove_player(p_obj)


    async def handle_player_command(self, player: Player, command_message: str):
        """
        Обрабатывает текстовую команду, полученную от игрока.

        Поддерживаемые команды:
            - SAY <сообщение>: Отправляет сообщение всем игрокам.
            - HELP: Показывает список доступных команд.
            - PLAYERS: Показывает список игроков в комнате.
            - QUIT: Инициирует выход игрока из комнаты.

        Args:
            player (Player): Игрок, отправивший команду.
            command_message (str): Строка с командой и ее аргументами.
        """
        parts = command_message.split(" ", 1) # Разделяем команду и аргументы
        command = parts[0].upper() # Команда приводится к верхнему регистру
        args = parts[1] if len(parts) > 1 else "" # Аргументы, если есть

        logger.info(f"Player {player.name} sent command: {command} with arguments: '{args}'")

        if command == "SAY":
            await self.broadcast_message(f"{player.name}: {args}") # Транслируем сообщение от имени игрока
        elif command == "HELP":
            await player.send_message("SERVER: Available commands: SAY <message>, PLAYERS, QUIT") # Already in English
        elif command == "PLAYERS":
            player_list = ", ".join(self.players.keys()) # Формируем список имен игроков
            await player.send_message(f"SERVER: Players in room: {player_list}") # Already in English
        elif command == "QUIT":
            await player.send_message("SERVER: You are leaving the room...") # Already in English
            # Фактическое удаление игрока (remove_player) будет вызвано из tcp_handler
            # при обнаружении закрытия соединения со стороны клиента или здесь.
            if player.writer and not player.writer.is_closing():
                player.writer.close() # Инициируем закрытие соединения со стороны сервера
                # await player.writer.wait_closed() # Ожидание может быть здесь или в tcp_handler
        # Сюда можно добавить другие игровые команды
        # Например, начало игры, ходы, использование способностей и т.д.
        else:
            await player.send_message(f"SERVER: Unknown command '{command}'. Type HELP for a list of commands.") # Already in English

    # Примеры методов для будущей более сложной игровой логики.
    # Они пока не реализованы и служат заглушками.
    async def start_match(self, player1: Player, player2: Player):
        """
        Заглушка для логики начала матча между двумя игроками.
        В реальной системе здесь бы инициализировалось состояние матча,
        уведомлялись игроки и т.д.
        """
        logger.info(f"Request to start match between {player1.name} and {player2.name} (not implemented).")
        # Логика начала матча
        pass

    async def record_match_result(self, winner: Player, loser: Player, details: str):
        """
        Заглушка для записи результата завершенного матча.
        Результаты могли бы сохраняться в `self.match_history` или внешней БД.
        """
        logger.info(f"Recording match result: winner {winner.name}, loser {loser.name}, details: {details} (not implemented).")
        # Запись результата матча
        self.match_history.append({
            "winner": winner.name,
            "loser": loser.name,
            "details": details,
            "timestamp": asyncio.get_event_loop().time() # Пример временной метки
        })
        pass
