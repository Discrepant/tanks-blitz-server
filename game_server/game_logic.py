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
        # Use a more robust way to get peername, checking if writer is None or closed
        player_addr_info = 'N/A (writer closed or None)'
        if player.writer and not player.writer.is_closing():
            try:
                player_addr_info = str(player.writer.get_extra_info('peername'))
            except Exception: # pragma: no cover
                player_addr_info = 'N/A (error getting peername)'

        logger.info(f"REMOVE_PLAYER: Attempting to remove player {player.name} (ID: {player.id}, Addr: {player_addr_info}). Current players: {list(self.players.keys())}")

        if player.name in self.players:
            del self.players[player.name]
            logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}) successfully removed from dict. Players remaining: {len(self.players)}")
            await self.broadcast_message(f"SERVER: Player {player.name} left the room.") # Already in English
        else:
            logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}) was not found in active players dict.")

        # Пытаемся корректно закрыть writer, если он существует и не закрывается
        if player.writer and not player.writer.is_closing():
            logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}). Closing writer in remove_player.")
            try:
                player.writer.close()
                await player.writer.wait_closed()
                logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}). Writer successfully closed in remove_player.")
            except Exception as e:
                logger.error(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}). Error closing writer in remove_player: {e}", exc_info=True)
        elif player.writer and player.writer.is_closing():
            logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}). Writer was already closing.")
        else:
            logger.info(f"REMOVE_PLAYER: Player {player.name} (ID: {player.id}). Writer is None or already closed, no action to close in remove_player.")


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
        # disconnected_players = [] # Список для игроков, у которых соединение было сброшено -> Handled by send_message or subsequent checks
        tasks = []
        # Создаем копию items для безопасной итерации, если self.players может изменяться
        for p_name, p_obj in list(self.players.items()): 
            if p_obj != exclude_player:
                # Player.send_message должен быть достаточно устойчив к ошибкам соединения,
                # логировать их и, возможно, закрывать свой writer.
                # Создаем задачу для каждой отправки, чтобы они выполнялись конкурентно.
                tasks.append(asyncio.create_task(p_obj.send_message(message)))

        if tasks:
            # Ожидаем завершения всех задач по отправке.
            # return_exceptions=True гарантирует, что все задачи будут выполнены,
            # даже если некоторые из них завершатся с ошибкой.
            # Ошибки логируются внутри Player.send_message.
            # Здесь можно добавить дополнительное логирование результатов gather, если необходимо.
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Эта ошибка уже должна быть залогирована в Player.send_message,
                    # но можно добавить дополнительный контекст здесь, если задача tasks[i] доступна для интроспекции.
                    logger.error(f"Broadcast task for a player resulted in an exception: {result}. This should have been handled within Player.send_message.")
                    # Логика по удалению игрока здесь может быть сложной, так как нужно сопоставить результат с игроком.
                    # Player.send_message уже должен закрывать writer при ошибке.
                    # Последующие операции или проверки активности должны будут убирать "мертвых" игроков.

        # Логика удаления отключившихся игроков может быть вынесена или усилена.
        # Player.send_message при ошибке закрывает свой writer.
        # Возможно, потребуется периодическая проверка "живых" соединений или при следующей попытке взаимодействия.
        # Текущая реализация remove_player вызывается из tcp_handler при IncompleteReadError/ConnectionResetError.


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
            player_addr_info_quit = 'N/A'
            if player.writer:
                try:
                    player_addr_info_quit = str(player.writer.get_extra_info('peername'))
                except Exception: # pragma: no cover
                    player_addr_info_quit = 'N/A (error getting peername)'

            logger.info(f"QUIT Command: Player {player.name} (ID: {player.id}, Addr: {player_addr_info_quit}). Processing QUIT.")
            try:
                await player.send_message("SERVER: You are leaving the room...")
                if player.writer and not player.writer.is_closing():
                    logger.info(f"QUIT Command: Player {player.name} (ID: {player.id}, Addr: {player_addr_info_quit}). Closing writer.")
                    player.writer.close()
                    await player.writer.wait_closed()
                    logger.info(f"QUIT Command: Player {player.name} (ID: {player.id}). Writer successfully closed.")
                elif player.writer and player.writer.is_closing():
                    logger.info(f"QUIT Command: Player {player.name} (ID: {player.id}). Writer was already closing.")
                else: # pragma: no cover
                    logger.info(f"QUIT Command: Player {player.name} (ID: {player.id}). Writer is None or already closed.")
            except Exception as e:
                logger.error(f"QUIT Command: Player {player.name} (ID: {player.id}). Error during writer close or send_message: {e}", exc_info=True)
            # Player removal will be handled by tcp_handler's finally block when readuntil() fails due to closed writer.
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
