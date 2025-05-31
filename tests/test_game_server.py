# tests/test_game_server.py
# Этот файл содержит модульные тесты для компонентов игрового сервера,
# таких как модели данных (Player), игровая логика (GameRoom)
# и обработчик TCP-соединений (handle_game_client).
# Примечание: Как и test_auth_server.py, эти тесты могут пересекаться
# с более новыми тестами в директории tests/unit/.

import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock, call # Инструменты для мокирования

# Добавляем путь к корневой директории проекта для корректного импорта модулей.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game_server.game_logic import GameRoom # Логика игровой комнаты
from game_server.models import Player # Модель игрока
from game_server.auth_client import AuthClient # Клиент аутентификации, необходим для GameRoom
from game_server.tcp_handler import handle_game_client # Обработчик TCP-соединений игрового сервера

class TestGameModels(unittest.TestCase):
    """
    Набор тестов для моделей данных игрового сервера, в частности для класса Player.
    Использует `unittest.TestCase` для синхронных тестов.
    Асинхронные методы модели Player тестируются с использованием `asyncio.run` или
    в асинхронных тестовых классах.
    """
    def test_player_creation(self):
        """
        Тест создания экземпляра Player.
        Проверяет, что ID игрока, имя, токен и writer корректно устанавливаются.
        """
        writer = MagicMock(spec=asyncio.StreamWriter) # Мок для StreamWriter
        player = Player(writer, "test_player", "test_token")
        self.assertIsNotNone(player.id, "ID игрока не должен быть None.")
        self.assertEqual(player.name, "test_player", "Имя игрока установлено неверно.")
        self.assertEqual(player.session_token, "test_token", "Токен сессии установлен неверно.")
        self.assertEqual(player.writer, writer, "Writer игрока установлен неверно.")

    # Для асинхронных методов Player лучше использовать IsolatedAsyncioTestCase,
    # но так как это уже часть существующего TestCase, можно обернуть вызовы.
    # Однако, более правильный подход - перенести асинхронные тесты в асинхронный класс.
    # Здесь для простоты оставим так, но с комментарием.
    def test_player_send_message_async_wrapper(self):
        """Обертка для асинхронного теста test_player_send_message."""
        asyncio.run(self._async_test_player_send_message())

    async def _async_test_player_send_message(self):
        """
        Тест успешной отправки сообщения игроку.
        Проверяет, что `writer.write` и `writer.drain` вызываются с правильными аргументами.
        """
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=False) # Writer не закрывается
        writer.write = MagicMock() # Мок для метода write
        writer.drain = AsyncMock() # Мок для асинхронного метода drain

        player = Player(writer, "test_player_send")
        await player.send_message("Hello")

        writer.write.assert_called_once_with(b"Hello\n") # Сообщение должно быть в байтах с \n
        writer.drain.assert_called_once()

    def test_player_send_message_writer_closed_async_wrapper(self):
        """Обертка для асинхронного теста test_player_send_message_writer_closed."""
        asyncio.run(self._async_test_player_send_message_writer_closed())

    async def _async_test_player_send_message_writer_closed(self):
        """
        Тест отправки сообщения при закрытом writer.
        Проверяет, что сообщение не отправляется, если writer закрыт.
        """
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=True) # Writer имитирует состояние "закрывается"
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        player = Player(writer, "test_player_closed_writer")
        await player.send_message("Hello Closed")

        writer.write.assert_not_called() # Сообщение не должно быть отправлено
        writer.drain.assert_not_called() # drain также не должен вызываться

    def test_player_send_message_connection_reset_async_wrapper(self):
        """Обертка для асинхронного теста test_player_send_message_connection_reset."""
        asyncio.run(self._async_test_player_send_message_connection_reset())
        
    async def _async_test_player_send_message_connection_reset(self):
        """
        Тест отправки сообщения при возникновении ConnectionResetError.
        Проверяет, что ошибка обрабатывается внутри `send_message` и writer закрывается.
        """
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.is_closing = MagicMock(return_value=False)
        # Имитируем ConnectionResetError при вызове writer.drain()
        writer.drain = AsyncMock(side_effect=ConnectionResetError("Connection reset by peer"))
        writer.write = MagicMock() # Сам по себе write не вызывает ошибку в этом тесте
        writer.close = MagicMock() # Мокируем close, который должен быть вызван в обработчике ошибки

        player = Player(writer, "test_player_conn_reset")

        # Ожидаем, что send_message обработает ConnectionResetError
        # и не выбросит его наружу (т.е. тест не должен упасть здесь).
        try:
            await player.send_message("Hello Connection Reset")
        except ConnectionResetError:
            self.fail("Метод send_message не должен распространять ConnectionResetError.")

        writer.write.assert_called_once_with(b"Hello Connection Reset\n")
        writer.drain.assert_called_once()
        # Проверяем, что writer.close() был вызван после обнаружения ошибки
        writer.close.assert_called_once()


class TestGameLogic(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для логики игровой комнаты (`game_server.game_logic.GameRoom`).
    Использует `unittest.IsolatedAsyncioTestCase` для асинхронных тестов.
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает мок для AuthClient и экземпляр GameRoom.
        Также создает моки StreamWriter для игроков.
        """
        # Мокируем AuthClient, так как GameRoom зависит от него.
        self.mock_auth_client = MagicMock(spec=AuthClient)
        self.game_room = GameRoom(auth_client=self.mock_auth_client)

        # Создаем мок-объекты StreamWriter для игроков
        self.player1_writer = AsyncMock(spec=asyncio.StreamWriter)
        self.player1_writer.is_closing.return_value = False # По умолчанию writer открыт
        self.player1_writer.get_extra_info.return_value = ('127.0.0.1', 10001) # Пример адреса

        self.player2_writer = AsyncMock(spec=asyncio.StreamWriter)
        self.player2_writer.is_closing.return_value = False
        self.player2_writer.get_extra_info.return_value = ('127.0.0.1', 10002)


    async def test_add_player(self):
        """
        Тест успешного добавления игрока в игровую комнату.
        Проверяет, что игрок добавляется в словарь `players` и получает приветственное сообщение.
        """
        player1 = Player(self.player1_writer, "player1_logic", "token1")
        await self.game_room.add_player(player1)
        self.assertIn("player1_logic", self.game_room.players, "Игрок должен быть в словаре игроков комнаты.")
        self.assertEqual(self.game_room.players["player1_logic"], player1, "Объект игрока в комнате не совпадает с добавленным.")
        # Проверяем, что сообщение о входе было отправлено игроку
        # (GameRoom.add_player отправляет "SERVER: Добро пожаловать...")
        self.player1_writer.write.assert_any_call("SERVER: Welcome to the game room!\n".encode('utf-8')) # English

    async def test_remove_player(self):
        """
        Тест удаления игрока из игровой комнаты.
        Проверяет, что игрок удаляется из словаря `players` и его writer закрывается.
        """
        player1 = Player(self.player1_writer, "player1_remove", "token_remove")
        await self.game_room.add_player(player1) # Сначала добавляем игрока
        self.assertIn("player1_remove", self.game_room.players, "Игрок должен быть добавлен перед удалением.")

        await self.game_room.remove_player(player1) # Удаляем игрока
        self.assertNotIn("player1_remove", self.game_room.players, "Игрок должен быть удален из словаря игроков.")
        # Проверяем, что writer игрока был закрыт
        self.player1_writer.close.assert_called_once()
        if hasattr(self.player1_writer, 'wait_closed'): # wait_closed может отсутствовать у простого MagicMock, но есть у AsyncMock
             self.player1_writer.wait_closed.assert_called_once()


    async def test_broadcast_message(self):
        """
        Тест широковещательной рассылки сообщений.
        Проверяет, что сообщение отправляется всем игрокам, кроме исключенного.
        """
        player1 = Player(self.player1_writer, "p1_broadcast", "t1_b")
        player2 = Player(self.player2_writer, "p2_broadcast", "t2_b")

        await self.game_room.add_player(player1)
        await self.game_room.add_player(player2)

        # Сбрасываем моки write/drain, чтобы отслеживать только вызовы из broadcast_message
        self.player1_writer.reset_mock()
        self.player2_writer.reset_mock()


        await self.game_room.broadcast_message("Test broadcast", exclude_player=player1)

        self.player1_writer.write.assert_not_called() # Исключенный игрок не должен получить сообщение
        self.player2_writer.write.assert_called_once_with(b"Test broadcast\n") # Второй игрок должен получить
        self.player2_writer.drain.assert_called_once() # drain должен быть вызван для второго игрока


    async def test_handle_player_command_say(self):
        """
        Тест обработки команды SAY от игрока.
        Проверяет, что сообщение игрока транслируется всем в комнате.
        """
        player1 = Player(self.player1_writer, "p1_cmd_say", "t_say1")
        player2 = Player(self.player2_writer, "p2_cmd_say", "t_say2")
        await self.game_room.add_player(player1)
        await self.game_room.add_player(player2)

        # Сбрасываем моки для чистоты теста, так как add_player уже делал вызовы write
        self.player1_writer.reset_mock()
        self.player2_writer.reset_mock()

        await self.game_room.handle_player_command(player1, "SAY Hello everyone")

        # Оба игрока (включая отправителя) должны получить сообщение "SAY"
        expected_msg = b"p1_cmd_say: Hello everyone\n"
        self.player1_writer.write.assert_called_once_with(expected_msg)
        self.player1_writer.drain.assert_called_once()
        self.player2_writer.write.assert_called_once_with(expected_msg)
        self.player2_writer.drain.assert_called_once()

    async def test_handle_player_command_players(self):
        """
        Тест обработки команды PLAYERS от игрока.
        Проверяет, что игроку отправляется список игроков в комнате.
        """
        player1 = Player(self.player1_writer, "p1_cmd_players", "t_players1")
        await self.game_room.add_player(player1)
        self.player1_writer.reset_mock() # Сброс после сообщений о входе от add_player

        await self.game_room.handle_player_command(player1, "PLAYERS")
        
        # Ожидаем сообщение со списком игроков.
        # Имя игрока 'p1_cmd_players' должно присутствовать в этом списке.
        # Захватываем аргумент вызова write и проверяем его содержимое.
        # Это более гибко, чем точное совпадение строки, если порядок игроков
        # в списке не гарантирован или если в комнате есть другие игроки (хотя здесь только один).
        self.assertTrue(self.player1_writer.write.called, "Метод write не был вызван для команды PLAYERS.")
        # call_args[0] - это кортеж позиционных аргументов, первый из которых - отправляемые байты.
        called_with_arg_bytes = self.player1_writer.write.call_args[0][0]
        called_with_arg_str = called_with_arg_bytes.decode('utf-8') 
        
        self.assertIn("SERVER: Players in room:", called_with_arg_str, "Ответ не содержит ожидаемый префикс.") # English
        self.assertIn("p1_cmd_players", called_with_arg_str, "Имя игрока отсутствует в списке.")


    async def test_authenticate_player_success_in_gameroom(self): # Переименовано для ясности
        """
        Тест успешной аутентификации игрока через GameRoom (используя мок AuthClient).
        """
        # Настраиваем мок AuthClient для возврата успешного результата аутентификации
        self.mock_auth_client.login_user = AsyncMock(return_value=(True, "Auth success", "fake_token"))

        authenticated, message, token = await self.game_room.authenticate_player("user_gs_auth", "pass_gs_auth")

        self.assertTrue(authenticated, "Аутентификация в GameRoom должна быть успешной.")
        self.assertEqual("Auth success", message, "Сообщение об успехе аутентификации неверно.")
        self.assertEqual("fake_token", token, "Токен сессии не совпадает.")
        # Проверяем, что метод login_user у мока AuthClient был вызван с правильными аргументами
        self.mock_auth_client.login_user.assert_called_once_with("user_gs_auth", "pass_gs_auth")

    async def test_authenticate_player_failure_in_gameroom(self): # Переименовано для ясности
        """
        Тест неудачной аутентификации игрока через GameRoom.
        """
        # Настраиваем мок AuthClient для возврата неудачного результата аутентификации
        self.mock_auth_client.login_user = AsyncMock(return_value=(False, "Auth failure", None))

        authenticated, message, token = await self.game_room.authenticate_player("user_gs_fail", "pass_gs_fail")

        self.assertFalse(authenticated, "Аутентификация в GameRoom должна завершиться неудачей.")
        self.assertEqual("Auth failure", message, "Сообщение о неудаче аутентификации неверно.")
        self.assertIsNone(token, "Токен сессии должен быть None при неудачной аутентификации.")
        self.mock_auth_client.login_user.assert_called_once_with("user_gs_fail", "pass_gs_fail")


class TestGameTcpHandler(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для TCP-обработчика игрового сервера (`game_server.tcp_handler.handle_game_client`).
    Тестирует логику обработки команд, аутентификации и взаимодействия с GameRoom.
    """

    def setUp(self):
        """
        Настройка перед каждым тестом.
        Создает мок AuthClient и мок GameRoom с мокированными методами.
        """
        self.mock_auth_client = AsyncMock(spec=AuthClient)
        # GameRoom теперь принимает auth_client в конструкторе.
        # Для тестов tcp_handler мы мокируем саму GameRoom, а не только ее auth_client.
        self.game_room = AsyncMock(spec=GameRoom) 
        # Мокируем методы GameRoom, которые будут вызываться из tcp_handler, чтобы изолировать тест.
        # self.game_room.authenticate_player = AsyncMock() # Уже мокировано через AsyncMock(spec=GameRoom)
        # self.game_room.add_player = AsyncMock()
        # self.game_room.remove_player = AsyncMock()
        # self.game_room.handle_player_command = AsyncMock()


    async def test_handle_game_client_login_success(self):
        """
        Тест успешного LOGIN через TCP-обработчик.
        Проверяет вызовы authenticate_player, Player (конструктор), add_player,
        отправку ответа клиенту и вызов remove_player при завершении.
        """
        reader = asyncio.StreamReader()
        reader.feed_data(b"LOGIN testuser password123\n") # Команда для TCP-обработчика
        reader.feed_eof() # Сигнализируем конец данных, чтобы цикл в хендлере завершился после одной итерации

        writer = AsyncMock(spec=asyncio.StreamWriter) # Используем AsyncMock для StreamWriter
        writer.get_extra_info.return_value = ('127.0.0.1', 54321) # Адрес клиента
        writer.is_closing.return_value = False # Writer открыт

        # Настраиваем мок game_room.authenticate_player для успешного входа
        self.game_room.authenticate_player.return_value = (True, "Login successful", "session_token_123") # English message

        # Используем patch для конструктора Player, чтобы проверить его вызов и вернуть мок-экземпляр.
        with patch('game_server.tcp_handler.Player', autospec=True) as MockPlayerConstructor:
            mock_player_instance = MockPlayerConstructor.return_value # Это будет мок объекта Player
            mock_player_instance.name = "testuser" # Устанавливаем имя для логов и сообщений
            mock_player_instance.id = "player_login_id_1" # Устанавливаем ID для мок-объекта
            mock_player_instance.writer = writer # Явно присваиваем writer мок-объекту
            # Мокируем метод send_message для созданного экземпляра Player, если он будет вызываться
            mock_player_instance.send_message = AsyncMock()


            # Запускаем handle_game_client с моком game_room.
            # Оборачивать reader и writer в try-finally не нужно, так как
            # handle_game_client должен сам корректно закрывать writer.
            await handle_game_client(reader, writer, self.game_room)


        # Проверки вызовов
        self.game_room.authenticate_player.assert_called_once_with("testuser", "password123")
        MockPlayerConstructor.assert_called_once_with(writer, "testuser", "session_token_123")
        self.game_room.add_player.assert_called_once_with(mock_player_instance)

        # Проверяем, что было отправлено сообщение об успешном логине
        # (tcp_handler отправляет это сообщение).
        writer.write.assert_any_call("LOGIN_SUCCESS Login successful Token: session_token_123\n".encode('utf-8')) # English

        # Проверяем, что remove_player был вызван при завершении работы хендлера
        # (даже если цикл команд не выполнился далее из-за reader.feed_eof()).
        self.game_room.remove_player.assert_called_once_with(mock_player_instance)
        writer.close.assert_called_once() # Writer должен быть закрыт
        writer.wait_closed.assert_called_once() # Ожидание закрытия writer'а


    async def test_handle_game_client_login_failure(self):
        """
        Тест неудачного LOGIN через TCP-обработчик.
        Проверяет, что Player не создается, add_player не вызывается,
        и клиенту отправляется сообщение об ошибке.
        """
        reader = asyncio.StreamReader()
        reader.feed_data(b"LOGIN testuser wrongpass\n")
        reader.feed_eof() # Завершаем поток после одной команды

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 54322)
        writer.is_closing.return_value = False

        # Настраиваем мок game_room.authenticate_player для неудачного входа
        self.game_room.authenticate_player.return_value = (False, "Incorrect password", None) # English message

        with patch('game_server.tcp_handler.Player', autospec=True) as MockPlayerConstructor:
            await handle_game_client(reader, writer, self.game_room)

        self.game_room.authenticate_player.assert_called_once_with("testuser", "wrongpass")
        MockPlayerConstructor.assert_not_called() # Конструктор Player не должен быть вызван
        self.game_room.add_player.assert_not_called() # Игрок не должен быть добавлен в комнату

        # Проверяем отправку сообщения о неудаче
        expected_calls = [
            call("SERVER_ACK_CONNECTED\n".encode('utf-8')),
            call("LOGIN_FAILURE Incorrect password\n".encode('utf-8'))
        ]
        writer.write.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(writer.write.call_count, len(expected_calls), "Количество вызовов writer.write не совпадает с ожидаемым")
        self.game_room.remove_player.assert_not_called() # Игрок не был добавлен, поэтому не должен удаляться
        writer.close.assert_called_once() # Соединение все равно должно быть закрыто
        writer.wait_closed.assert_called_once()


    async def test_handle_game_client_commands_after_login(self):
        """
        Тест обработки команд (например, SAY) после успешного логина.
        Проверяет, что команды передаются в game_room.handle_player_command.
        """
        reader = asyncio.StreamReader()
        # Последовательность: успешный логин, затем команда SAY
        reader.feed_data(b"LOGIN gooduser goodpass\nSAY Hello there\n")
        # Не закрываем поток сразу (feed_eof()), чтобы проверить цикл обработки команд.
        # Вместо этого, будем имитировать закрытие соединения клиентом через readuntil.

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info.return_value = ('127.0.0.1', 54323)
        # is_closing будет False для первой и второй итерации цикла, затем True для выхода
        writer.is_closing.side_effect = [False, False, True] 

        # Настраиваем успешную аутентификацию
        self.game_room.authenticate_player.return_value = (True, "Вход выполнен", "token_xyz")

        # Создаем мок-объект игрока, который будет "создан" после логина
        mock_created_player = AsyncMock(spec=Player) # Используем AsyncMock, если Player имеет async методы
        mock_created_player.name = "gooduser"
        mock_created_player.id = "player_commands_id_1" # Устанавливаем ID для мок-объекта
        mock_created_player.writer = writer # Важно, чтобы у мока игрока был ассоциированный writer

        with patch('game_server.tcp_handler.Player', return_value=mock_created_player) as MockPlayerConstructor:
            # Чтобы цикл while в tcp_handler корректно обработал команды и завершился,
            # нужно правильно настроить reader.readuntil.
            # Первая команда - LOGIN (уже в reader.feed_data).
            # Вторая команда - SAY (также в reader.feed_data).
            # После второй команды имитируем закрытие соединения клиентом (IncompleteReadError).
            
            # Устанавливаем side_effect для readuntil, чтобы он возвращал команды по очереди
            # и затем имитировал закрытие соединения.
            async def read_side_effect(*args, **kwargs):
                if not hasattr(read_side_effect, 'call_count'):
                    read_side_effect.call_count = 0
                read_side_effect.call_count += 1
                
                if read_side_effect.call_count == 1: # Первая команда (LOGIN)
                    return b"LOGIN gooduser goodpass\n" # Это уже было в feed_data, но для явности
                elif read_side_effect.call_count == 2: # Вторая команда (SAY)
                    return b"SAY Hello there\n"
                elif read_side_effect.call_count == 3: # После обработки SAY, имитируем закрытие
                    raise asyncio.IncompleteReadError(b'', 0) # Клиент закрыл соединение
                # Эта проверка нужна, чтобы тест не завис, если readuntil вызывается больше раз, чем ожидалось
                raise AssertionError(f"readuntil вызван слишком много раз ({read_side_effect.call_count})")

            reader.readuntil = AsyncMock(side_effect=read_side_effect)


            await handle_game_client(reader, writer, self.game_room)

        # Проверки
        MockPlayerConstructor.assert_called_once_with(writer=writer, name="gooduser", session_token="token_xyz") # Keyword args
        self.game_room.add_player.assert_called_once_with(mock_created_player) # Проверка добавления в комнату
        
        # Проверяем, что handle_player_command была вызвана с правильными аргументами для команды SAY
        self.game_room.handle_player_command.assert_called_once_with(mock_created_player, "SAY Hello there")

        # Проверяем, что remove_player был вызван при завершении (из-за IncompleteReadError)
        self.game_room.remove_player.assert_called_once_with(mock_created_player)
        writer.close.assert_called_once() # Writer должен быть закрыт
        writer.wait_closed.assert_called_once() # Ожидание закрытия


if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую.
    unittest.main()
