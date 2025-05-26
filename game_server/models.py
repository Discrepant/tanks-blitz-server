import asyncio

# Глобальный счетчик для ID игроков, чтобы они были уникальны в рамках сессии сервера
_next_player_id = 1

class Player:
    def __init__(self, writer: asyncio.StreamWriter, name: str, session_token: str = None):
        global _next_player_id
        self.id = _next_player_id
        _next_player_id += 1
        self.writer = writer
        self.name = name
        self.session_token = session_token # Может быть None, если аутентификация не используется или не удалась
        self.current_match_id = None # ID матча, в котором игрок участвует

    async def send_message(self, message: str):
        if self.writer and not self.writer.is_closing():
            try:
                self.writer.write(message.encode() + b"\n") # Добавляем \n для разделения сообщений
                await self.writer.drain()
            except ConnectionResetError:
                print(f"ConnectionResetError: Не удалось отправить сообщение игроку {self.name} (ID: {self.id}). Соединение сброшено.")
                # Здесь можно обработать ошибку, например, пометить игрока для удаления
                if self.writer and not self.writer.is_closing():
                    self.writer.close() # Закрываем writer, если он еще открыт
            except Exception as e:
                print(f"Ошибка при отправке сообщения игроку {self.name} (ID: {self.id}): {e}")
                # Аналогично, обработка других ошибок отправки
                if self.writer and not self.writer.is_closing():
                    self.writer.close()
        else:
            print(f"Не могу отправить сообщение игроку {self.name} (ID: {self.id}): writer закрыт или отсутствует.")

    def __str__(self):
        return f"Player(id={self.id}, name='{self.name}', token_present={self.session_token is not None})"

    def __repr__(self):
        return self.__str__()

class Match:
    def __init__(self, match_id: int, player1: Player, player2: Player):
        self.match_id = match_id
        self.players = [player1, player2]
        self.current_turn_player = player1 # Начинает первый игрок
        self.board = [[" " for _ in range(3)] for _ in range(3)] # Пример для крестиков-ноликов
        self.winner = None
        self.is_draw = False
        self.is_active = True

    async def broadcast_to_match_players(self, message: str):
        for player in self.players:
            await player.send_message(message)

    # Другие методы, специфичные для логики матча (например, сделать ход, проверить победителя)
    # ...
