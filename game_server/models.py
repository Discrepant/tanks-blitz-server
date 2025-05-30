# game_server/models.py
# Этот модуль определяет модели данных, используемые на игровом сервере,
# такие как Player (игрок) и Match (матч).
import asyncio
import logging # Добавляем логирование

logger = logging.getLogger(__name__) # Инициализация логгера

# Глобальный счетчик для ID игроков. Обеспечивает уникальность ID игроков
# в рамках текущей сессии (запуска) сервера.
# В более сложной системе ID могли бы генерироваться базой данных или UUID.
_next_player_id = 1

class Player:
    """
    Представляет игрока на сервере.

    Содержит информацию об ID игрока, его имени, сетевом соединении (writer),
    токене сессии и ID текущего матча.

    Атрибуты:
        id (int): Уникальный идентификатор игрока.
        writer (asyncio.StreamWriter): Объект для отправки данных игроку.
        name (str): Имя игрока.
        session_token (str, optional): Токен сессии, полученный от сервера аутентификации.
                                       Может быть None.
        current_match_id (int, optional): ID матча, в котором игрок участвует.
                                          Может быть None, если игрок не в матче.
    """
    def __init__(self, writer: asyncio.StreamWriter, name: str, session_token: str = None):
        """
        Инициализирует объект игрока.

        Args:
            writer (asyncio.StreamWriter): StreamWriter для отправки сообщений игроку.
            name (str): Имя игрока.
            session_token (str, optional): Токен сессии. По умолчанию None.
        """
        global _next_player_id # Используем глобальный счетчик для ID
        self.id = _next_player_id
        _next_player_id += 1 # Увеличиваем счетчик для следующего игрока
        self.writer = writer
        self.name = name
        # Токен сессии может быть None, если аутентификация не используется
        # или не удалась на каком-то этапе.
        self.session_token = session_token 
        # ID матча, в котором игрок участвует. None, если игрок не в матче.
        self.current_match_id = None 

    async def send_message(self, message: str):
        """
        Асинхронно отправляет сообщение игроку.

        Кодирует сообщение в UTF-8 и добавляет символ новой строки для разделения.
        Обрабатывает ошибки ConnectionResetError и другие исключения при отправке.

        Args:
            message (str): Сообщение для отправки.
        """
        if self.writer and not self.writer.is_closing(): # Проверяем, что writer существует и не закрывается
            try:
                # Добавляем символ новой строки, чтобы клиент мог использовать readuntil(b'\n')
                self.writer.write(message.encode('utf-8') + b"\n") 
                # Ожидаем, пока буфер записи не будет очищен, с таймаутом
                await asyncio.wait_for(self.writer.drain(), timeout=5.0)
                logger.debug(f"Сообщение успешно отправлено игроку {self.name} (ID: {self.id}): {message}")
            except asyncio.TimeoutError:
                logger.error(f"TimeoutError: Таймаут (5s) при ожидании drain для игрока {self.name} (ID: {self.id}). Закрытие соединения.")
                if self.writer and not self.writer.is_closing():
                    self.writer.close()
            except ConnectionResetError:
                logger.warning(f"ConnectionResetError: Не удалось отправить сообщение игроку {self.name} (ID: {self.id}). Соединение сброшено.")
                if self.writer and not self.writer.is_closing():
                    self.writer.close() # Закрываем writer, если он еще открыт и произошла ошибка
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения игроку {self.name} (ID: {self.id}): {e}", exc_info=True)
                if self.writer and not self.writer.is_closing():
                    self.writer.close()
        else:
            logger.warning(f"Не могу отправить сообщение игроку {self.name} (ID: {self.id}): writer закрыт или отсутствует.")

    def __str__(self):
        """Возвращает строковое представление объекта Player."""
        token_status = "присутствует" if self.session_token is not None else "отсутствует"
        return f"Player(id={self.id}, name='{self.name}', токен_сессии={token_status}, текущий_матч_id={self.current_match_id})"

    def __repr__(self):
        """Возвращает официальное строковое представление объекта Player."""
        return self.__str__()

class Match:
    """
    Представляет игровой матч между двумя игроками.

    Содержит информацию об ID матча, участвующих игроках, текущем ходе,
    игровом поле (на примере крестиков-ноликов), победителе и статусе матча.
    Это примерная структура, которая может быть расширена для более сложной игры.

    Атрибуты:
        match_id (int): Уникальный идентификатор матча.
        players (list[Player]): Список из двух объектов Player, участвующих в матче.
        current_turn_player (Player): Игрок, чей сейчас ход.
        board (list[list[str]]): Игровое поле (пример для крестиков-ноликов 3x3).
        winner (Player, optional): Победитель матча. None, если победителя еще нет.
        is_draw (bool): True, если матч завершился вничью.
        is_active (bool): True, если матч активен. False, если завершен.
    """
    def __init__(self, match_id: int, player1: Player, player2: Player):
        """
        Инициализирует объект матча.

        Args:
            match_id (int): ID матча.
            player1 (Player): Первый игрок.
            player2 (Player): Второй игрок.
        """
        self.match_id = match_id
        self.players = [player1, player2]
        self.current_turn_player = player1 # По умолчанию начинает первый игрок
        # Пример игрового поля для крестиков-ноликов.
        # В реальной игре структура поля будет зависеть от типа игры.
        self.board = [[" " for _ in range(3)] for _ in range(3)] 
        self.winner = None # Победитель (объект Player) или None
        self.is_draw = False # Флаг ничьей
        self.is_active = True # Флаг активности матча
        logger.info(f"Матч {match_id} создан между {player1.name} и {player2.name}.")

    async def broadcast_to_match_players(self, message: str):
        """
        Асинхронно отправляет сообщение обоим игрокам в матче.

        Args:
            message (str): Сообщение для отправки.
        """
        logger.debug(f"Трансляция сообщения игрокам матча {self.match_id}: {message}")
        for player in self.players:
            await player.send_message(message)

    # Сюда можно добавить другие методы, специфичные для логики конкретного матча,
    # например:
    # - async def make_move(self, player: Player, move_details: dict): обработка хода игрока
    # - async def check_win_condition(self): проверка условий победы/ничьей
    # - async def end_match(self, winner: Player = None, is_draw: bool = False): завершение матча
    # ...
    pass
