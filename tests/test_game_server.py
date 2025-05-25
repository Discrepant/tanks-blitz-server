import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# Добавляем путь к корневой директории проекта
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game_server.game_logic import GameRoom
from game_server.models import Player
from game_server.auth_client import AuthClient # Нужен для GameRoom
from game_server.tcp_handler import handle_game_client

class TestGameModels(unittest.TestCase):
    def test_player_creation(self):
        writer = MagicMock(spec=asyncio.StreamWriter)
        player = Player(writer, "test_player", "test_token")
        self.assertIsNotNone(player.id)
        self.assertEqual(player.name, "test_player")
        self.assertEqual(player.session_token, "test_token")
        self.assertEqual(player.writer, writer)

    async def test_player_send_message(self):
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=False)
        writer.write = MagicMock()
        # Мокаем drain как асинхронную функцию
        writer.drain = AsyncMock()


        player = Player(writer, "test_player")
        await player.send_message("Hello")

        writer.write.assert_called_once_with(b"Hello\n")
        writer.drain.assert_called_once()

    async def test_player_send_message_writer_closed(self):
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=True) # Writer закрывается
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        player = Player(writer, "test_player_closed_writer")
        await player.send_message("Hello Closed")

        writer.write.assert_not_called() # Сообщение не должно быть отправлено
        writer.drain.assert_not_called()

    async def test_player_send_message_connection_reset(self):
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=False)
        # Имитируем ConnectionResetError при вызове writer.drain()
        writer.drain = AsyncMock(side_effect=ConnectionResetError("Connection reset by peer"))
        writer.write = MagicMock() # write сам по себе не вызывает ошибку в этом тесте
        writer.close = MagicMock() # Мокаем close, который будет вызван в обработчике ошибки

        player = Player(writer, "test_player_conn_reset")

        # Ожидаем, что send_message обработает ConnectionResetError
        # и не выбросит его наружу
        try:
            await player.send_message("Hello Connection Reset")
        except ConnectionResetError:
            self.fail("send_message should not propagate ConnectionResetError")

        writer.write.assert_called_once_with(b"Hello Connection Reset\n")
        writer.drain.assert_called_once()
        # Проверяем, что writer.close() был вызван после ошибки
        writer.close.assert_called_once()


class TestGameLogic(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Мокаем AuthClient для GameRoom
        self.mock_auth_client = MagicMock(spec=AuthClient)
        self.game_room = GameRoom(auth_client=self.mock_auth_client)

        # Создаем мок writer'а для игроков
        self.player1_writer = AsyncMock(spec=asyncio.StreamWriter)
        self.player1_writer.is_closing.return_value = False
        self.player1_writer.get_extra_info.return_value = ('127.0.0.1', 10001)

        self.player2_writer = AsyncMock(spec=asyncio.StreamWriter)
        self.player2_writer.is_closing.return_value = False
        self.player2_writer.get_extra_info.return_value = ('127.0.0.1', 10002)


    async def test_add_player(self):
        player1 = Player(self.player1_writer, "player1_logic", "token1")
        await self.game_room.add_player(player1)
        self.assertIn("player1_logic", self.game_room.players)
        self.assertEqual(self.game_room.players["player1_logic"], player1)
        # Проверяем, что сообщение о входе было отправлено игроку
        player1.writer.write.assert_any_call(b"SERVER: Добро пожаловать в игровую комнату!\n")

    async def test_remove_player(self):
        player1 = Player(self.player1_writer, "player1_remove", "token_remove")
        await self.game_room.add_player(player1)
        self.assertIn("player1_remove", self.game_room.players)

        await self.game_room.remove_player(player1)
        self.assertNotIn("player1_remove", self.game_room.players)
        # Проверяем, что writer был закрыт
        player1.writer.close.assert_called_once()
        if hasattr(player1.writer, 'wait_closed'): # wait_closed может быть не всегда у мока
             player1.writer.wait_closed.assert_called_once()


    async def test_broadcast_message(self):
        player1 = Player(self.player1_writer, "p1_broadcast", "t1_b")
        player2 = Player(self.player2_writer, "p2_broadcast", "t2_b")

        await self.game_room.add_player(player1)
        await self.game_room.add_player(player2)

        # Сбрасываем моки write/drain, чтобы отслеживать только вызовы из broadcast
        player1.writer.reset_mock()
        player2.writer.reset_mock()


        await self.game_room.broadcast_message("Test broadcast", exclude_player=player1)

        player1.writer.write.assert_not_called() # Исключенный игрок не получает
        player2.writer.write.assert_called_once_with(b"Test broadcast\n")
        player2.writer.drain.assert_called_once()


    async def test_handle_player_command_say(self):
        player1 = Player(self.player1_writer, "p1_cmd_say", "t_say1")
        player2 = Player(self.player2_writer, "p2_cmd_say", "t_say2")
        await self.game_room.add_player(player1)
        await self.game_room.add_player(player2)

        # Сбрасываем моки для чистоты теста
        player1.writer.reset_mock()
        player2.writer.reset_mock()

        await self.game_room.handle_player_command(player1, "SAY Hello everyone")

        # Оба игрока должны получить сообщение "SAY"
        expected_msg = b"p1_cmd_say: Hello everyone\n"
        player1.writer.write.assert_called_once_with(expected_msg)
        player1.writer.drain.assert_called_once()
        player2.writer.write.assert_called_once_with(expected_msg)
        player2.writer.drain.assert_called_once()

    async def test_handle_player_command_players(self):
        player1 = Player(self.player1_writer, "p1_cmd_players", "t_players1")
        await self.game_room.add_player(player1)
        player1.writer.reset_mock() # Сброс после сообщений о входе

        await self.game_room.handle_player_command(player1, "PLAYERS")
        # Ожидаем сообщение со списком игроков
        # Имя игрока 'p1_cmd_players' должно быть в списке
        # Захватываем аргумент вызова write и проверяем его содержимое
        # Это более гибко, чем точное совпадение строки, если порядок не гарантирован
        # или есть другие игроки (хотя здесь только один)
        self.assertTrue(player1.writer.write.called)
        called_with_arg = player1.writer.write.call_args[0][0].decode() # Получаем строку
        self.assertIn("SERVER: Игроки в комнате:", called_with_arg)
        self.assertIn("p1_cmd_players", called_with_arg)


    async def test_authenticate_player_success(self):
        # Настраиваем мок AuthClient для успешной аутентификации
        self.mock_auth_client.login_user = AsyncMock(return_value=(True, "Auth success", "fake_token"))

        authenticated, message, token = await self.game_room.authenticate_player("user_gs_auth", "pass_gs_auth")

        self.assertTrue(authenticated)
        self.assertEqual("Auth success", message)
        self.assertEqual("fake_token", token)
        self.mock_auth_client.login_user.assert_called_once_with("user_gs_auth", "pass_gs_auth")

    async def test_authenticate_player_failure(self):
        # Настраиваем мок AuthClient для неудачной аутентификации
        self.mock_auth_client.login_user = AsyncMock(return_value=(False, "Auth failure", None))

        authenticated, message, token = await self.game_room.authenticate_player("user_gs_fail", "pass_gs_fail")

        self.assertFalse(authenticated)
        self.assertEqual("Auth failure", message)
        self.assertIsNone(token)
        self.mock_auth_client.login_user.assert_called_once_with("user_gs_fail", "pass_gs_fail")


class TestGameTcpHandler(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_auth_client = AsyncMock(spec=AuthClient)
        # GameRoom теперь принимает auth_client в конструкторе
        self.game_room = GameRoom(auth_client=self.mock_auth_client)
        # Мокаем методы GameRoom, которые будут вызываться из tcp_handler
        self.game_room.authenticate_player = AsyncMock()
        self.game_room.add_player = AsyncMock()
        self.game_room.remove_player = AsyncMock()
        self.game_room.handle_player_command = AsyncMock()


    async def test_handle_game_client_login_success(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"LOGIN testuser password123\n") # Команда для TCP хендлера
        reader.feed_eof()

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 54321)
        writer.is_closing.return_value = False # Важно для основного цикла while

        # Настраиваем мок authenticate_player для успешного входа
        self.game_room.authenticate_player.return_value = (True, "Успешный вход", "session_token_123")

        # Используем patch для Player, чтобы проверить его создание
        with patch('game_server.tcp_handler.Player', autospec=True) as MockPlayer:
            mock_player_instance = MockPlayer.return_value
            mock_player_instance.name = "testuser" # Для логов и сообщений
            # Мокаем send_message для экземпляра Player
            mock_player_instance.send_message = AsyncMock()


            # Запускаем handle_game_client с моком game_room
            # Оборачиваем reader и writer в try-finally не нужно, т.к. handle_game_client должен сам закрывать writer
            await handle_game_client(reader, writer, self.game_room)


        self.game_room.authenticate_player.assert_called_once_with("testuser", "password123")
        MockPlayer.assert_called_once_with(writer, "testuser", "session_token_123")
        self.game_room.add_player.assert_called_once_with(mock_player_instance)

        # Проверяем, что было отправлено сообщение об успешном логине
        writer.write.assert_any_call(b"LOGIN_SUCCESS Успешный вход Token: session_token_123\n")

        # Проверяем, что remove_player был вызван при завершении работы хендлера
        # (даже если цикл команд не выполнился из-за reader.feed_eof())
        self.game_room.remove_player.assert_called_once_with(mock_player_instance)
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()


    async def test_handle_game_client_login_failure(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b"LOGIN testuser wrongpass\n")
        reader.feed_eof()

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 54322)
        writer.is_closing.return_value = False


        self.game_room.authenticate_player.return_value = (False, "Неверный пароль", None)

        with patch('game_server.tcp_handler.Player', autospec=True) as MockPlayer:
            await handle_game_client(reader, writer, self.game_room)

        self.game_room.authenticate_player.assert_called_once_with("testuser", "wrongpass")
        MockPlayer.assert_not_called() # Player не должен быть создан
        self.game_room.add_player.assert_not_called() # Игрок не должен быть добавлен

        writer.write.assert_called_once_with(b"LOGIN_FAILURE Неверный пароль\n")
        self.game_room.remove_player.assert_not_called() # Игрок не был добавлен, не должен удаляться
        writer.close.assert_called_once() # Соединение все равно должно быть закрыто
        writer.wait_closed.assert_called_once()


    async def test_handle_game_client_commands_after_login(self):
        reader = asyncio.StreamReader()
        # Сначала успешный логин, потом команда
        reader.feed_data(b"LOGIN gooduser goodpass\nSAY Hello there\n")
        # reader.feed_eof() # Не закрываем поток сразу, чтобы проверить цикл команд

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 54323)
        writer.is_closing.side_effect = [False, False, True] # False для цикла, True для выхода

        self.game_room.authenticate_player.return_value = (True, "Вход выполнен", "token_xyz")

        # Создаем мок игрока, который будет возвращен MockPlayer
        mock_created_player = AsyncMock(spec=Player)
        mock_created_player.name = "gooduser"
        mock_created_player.writer = writer # Важно, чтобы у мока игрока был writer

        with patch('game_server.tcp_handler.Player', return_value=mock_created_player) as MockPlayerConstructor:
            # Чтобы цикл while в tcp_handler прервался после команды SAY,
            # мы можем заставить reader.readuntil(b"\n") выбросить исключение после первой команды.
            # Или, что проще, reader.feed_eof() после данных для команд.
            async def read_side_effect(*args, **kwargs):
                if read_side_effect.call_count == 1:
                    return b"SAY Hello there\n"
                elif read_side_effect.call_count == 2: # После команды SAY, имитируем закрытие соединения клиентом
                    # reader.feed_eof() здесь не сработает, т.к. это внутренняя логика StreamReader
                    # Проще выбросить IncompleteReadError, как будто клиент закрыл соединение
                    raise asyncio.IncompleteReadError(b'', 0)
                raise AssertionError("readuntil called too many times")
            read_side_effect.call_count = 0
            reader.readuntil = AsyncMock(side_effect=read_side_effect)


            await handle_game_client(reader, writer, self.game_room)

        MockPlayerConstructor.assert_called_once_with(writer, "gooduser", "token_xyz")
        self.game_room.add_player.assert_called_once_with(mock_created_player)
        # Проверяем, что handle_player_command была вызвана с правильными аргументами
        self.game_room.handle_player_command.assert_called_once_with(mock_created_player, "SAY Hello there")

        # Проверяем, что remove_player был вызван
        self.game_room.remove_player.assert_called_once_with(mock_created_player)
        writer.close.assert_called_once()
        writer.wait_closed.assert_called_once()


if __name__ == '__main__':
    unittest.main()
