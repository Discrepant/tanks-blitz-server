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
            # Отправляем сообщение об этом игроку.
            logger.warning(f"Игрок {player.name} уже существует. Отправка сообщения.") # Player {player.name} already exists. Sending message.
            await player.send_message(f"СЕРВЕР: Игрок с именем '{player.name}' уже находится в комнате. Новое подключение не создано.")
            # Возможно, стоит рассмотреть закрытие старого соединения или обновление writer для существующего игрока.
            return

        self.players[player.name] = player
        logger.info(f"Игрок {player.name} (ID: {player.id}) добавлен в игровую комнату. Всего игроков: {len(self.players)}") # Player {player.name} (ID: {player.id}) added to game room. Total players: {len(self.players)}
        await player.send_message("СЕРВЕР: Добро пожаловать в игровую комнату!")
        await self.broadcast_message(f"СЕРВЕР: Игрок {player.name} присоединился к комнате.", exclude_player=player)

    async def remove_player(self, player: Player):
        """
        Удаляет игрока из игровой комнаты.

        Если игрок найден, он удаляется из словаря `self.players`,
        и остальные игроки уведомляются о его выходе.
        Также производится попытка закрыть сетевое соединение игрока.

        Args:
            player (Player): Объект игрока для удаления.
        """
        # Более надежный способ получить peername, проверяя, что writer не None и не закрыт
        player_addr_info = 'Н/Д (writer закрыт или None)' # N/A (writer closed or None)
        if player.writer and not player.writer.is_closing():
            try:
                player_addr_info = str(player.writer.get_extra_info('peername'))
            except Exception: # pragma: no cover
                player_addr_info = 'Н/Д (ошибка получения peername)' # N/A (error getting peername)

        logger.info(f"REMOVE_PLAYER: Попытка удалить игрока {player.name} (ID: {player.id}, Addr: {player_addr_info}). Текущие игроки: {list(self.players.keys())}") # Attempting to remove player... Current players...

        if player.name in self.players:
            del self.players[player.name]
            logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}) успешно удален из словаря. Осталось игроков: {len(self.players)}") # Player ... successfully removed from dict. Players remaining: ...
            await self.broadcast_message(f"СЕРВЕР: Игрок {player.name} покинул комнату.")
        else:
            logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}) не найден в словаре активных игроков.") # Player ... was not found in active players dict.

        # Пытаемся корректно закрыть writer, если он существует и не закрывается
        if player.writer and not player.writer.is_closing():
            logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}). Закрытие writer в remove_player.") # Closing writer in remove_player.
            try:
                player.writer.close()
                await player.writer.wait_closed()
                logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}). Writer успешно закрыт в remove_player.") # Writer successfully closed in remove_player.
            except Exception as e:
                logger.error(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}). Ошибка при закрытии writer в remove_player: {e}", exc_info=True) # Error closing writer in remove_player:
        elif player.writer and player.writer.is_closing(): # writer уже закрывается
            logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}). Writer уже находился в процессе закрытия.") # Writer was already closing.
        else: # writer равен None или уже закрыт
            logger.info(f"REMOVE_PLAYER: Игрок {player.name} (ID: {player.id}). Writer равен None или уже закрыт, действие по закрытию в remove_player не требуется.") # Writer is None or already closed, no action to close in remove_player.


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
        # disconnected_players = [] # Список для игроков, у которых соединение было сброшено -> Обрабатывается send_message или последующими проверками
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
                    logger.error(f"Задача трансляции для игрока завершилась исключением: {result}. Это должно было быть обработано в Player.send_message.") # Broadcast task for a player resulted in an exception: {result}. This should have been handled within Player.send_message.
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

        logger.info(f"Игрок {player.name} отправил команду: {command} с аргументами: '{args}'") # Player ... sent command ... with arguments ...

        if command == "SAY":
            await self.broadcast_message(f"{player.name}: {args}") # Транслируем сообщение от имени игрока
        elif command == "HELP":
            await player.send_message("СЕРВЕР: Доступные команды: SAY <сообщение>, PLAYERS, QUIT")
        elif command == "PLAYERS":
            player_list = ", ".join(self.players.keys()) # Формируем список имен игроков
            await player.send_message(f"СЕРВЕР: Игроки в комнате: {player_list}")
        elif command == "QUIT":
            player_addr_info_quit = 'Н/Д' # N/A
            if player.writer:
                try:
                    player_addr_info_quit = str(player.writer.get_extra_info('peername'))
                except Exception: # pragma: no cover
                    player_addr_info_quit = 'Н/Д (ошибка получения peername)' # N/A (error getting peername)

            logger.info(f"Команда QUIT: Игрок {player.name} (ID: {player.id}, Addr: {player_addr_info_quit}). Обработка QUIT.") # QUIT Command: Player ... Processing QUIT.
            try:
                await player.send_message("СЕРВЕР: Вы покидаете комнату...")
                if player.writer and not player.writer.is_closing():
                    logger.info(f"Команда QUIT: Игрок {player.name} (ID: {player.id}, Addr: {player_addr_info_quit}). Закрытие writer.") # Closing writer.
                    player.writer.close()
                    await player.writer.wait_closed()
                    logger.info(f"Команда QUIT: Игрок {player.name} (ID: {player.id}). Writer успешно закрыт.") # Writer successfully closed.
                elif player.writer and player.writer.is_closing(): # writer уже закрывается
                    logger.info(f"Команда QUIT: Игрок {player.name} (ID: {player.id}). Writer уже находился в процессе закрытия.") # Writer was already closing.
                else: # pragma: no cover # writer равен None или уже закрыт
                    logger.info(f"Команда QUIT: Игрок {player.name} (ID: {player.id}). Writer равен None или уже закрыт.") # Writer is None or already closed.
            except Exception as e:
                logger.error(f"Команда QUIT: Игрок {player.name} (ID: {player.id}). Ошибка во время закрытия writer или send_message: {e}", exc_info=True) # Error during writer close or send_message:
            # Удаление игрока будет обработано в блоке finally tcp_handler, когда readuntil() завершится ошибкой из-за закрытого writer.
        # Сюда можно добавить другие игровые команды
        # Например, начало игры, ходы, использование способностей и т.д.
        else:
            await player.send_message(f"СЕРВЕР: Неизвестная команда '{command}'. Введите HELP для списка команд.")

    # Примеры методов для будущей более сложной игровой логики.
    # Они пока не реализованы и служат заглушками.
    async def start_match(self, player1: Player, player2: Player):
        """
        Заглушка для логики начала матча между двумя игроками.
        В реальной системе здесь бы инициализировалось состояние матча,
        уведомлялись игроки и т.д.
        """
        logger.info(f"Запрос на начало матча между {player1.name} и {player2.name} (не реализовано).") # Request to start match between ... (not implemented).
        # Логика начала матча
        pass

    async def record_match_result(self, winner: Player, loser: Player, details: str):
        """
        Заглушка для записи результата завершенного матча.
        Результаты могли бы сохраняться в `self.match_history` или внешней БД.
        """
        logger.info(f"Запись результата матча: победитель {winner.name}, проигравший {loser.name}, детали: {details} (не реализовано).") # Recording match result: winner ..., loser ..., details: ... (not implemented).
        # Запись результата матча
        self.match_history.append({
            "winner": winner.name,
            "loser": loser.name,
            "details": details,
            "timestamp": asyncio.get_event_loop().time() # Пример временной метки
        })
        pass
