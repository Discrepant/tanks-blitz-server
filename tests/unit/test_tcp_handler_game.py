# tests/unit/test_tcp_handler_game.py
# tests/unit/test_tcp_handler_game.py
# Этот файл содержит модульные тесты для TCP-обработчика игрового сервера
# (game_server.tcp_handler.handle_game_client).
# Основное внимание уделяется проверке корректности публикации команд в RabbitMQ.

import logging
# Настройка базового логирования для тестов. Помогает отслеживать ход выполнения тестов.
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')

import asyncio
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock # Инструменты для мокирования

# Импортируем тестируемую функцию
from game_server.tcp_handler import handle_game_client 
# Предполагается, что Player и GameRoom либо более сложны и тестируются отдельно,
# либо их поведение полностью мокируется в этих тестах.
# Фокус здесь на проверке взаимодействия с RabbitMQ (через mock_publish_rabbitmq).
# from game_server.game_logic import Player, GameRoom # Закомментировано, так как используются моки

class MockPlayer:
    """
    Упрощенный мок-класс для Player.
    Используется для имитации объекта игрока в тестах TCP-обработчика.
    Содержит основные атрибуты и асинхронный метод send_message.
    """
    def __init__(self, writer, name="test_player", token="test_token", id="mock_player_id"): # Добавлен параметр id
        self.writer = writer # Объект StreamWriter для отправки сообщений игроку
        self.name = name # Имя игрока
        self.token = token # Токен сессии игрока
        self.id = id # ID игрока, добавлен для тестов
        self.address = ("127.0.0.1", 12345) # Пример адреса клиента

    async def send_message(self, message: str):
        """
        Асинхронно отправляет сообщение игроку.
        Имитирует поведение реального метода Player.send_message.
        """
        if self.writer and not self.writer.is_closing(): # Если writer существует и не закрывается
            self.writer.write(message.encode('utf-8') + b"\n") # Отправляем сообщение с новой строкой
            await self.writer.drain() # Ожидаем сброса буфера

# Используем AsyncMock для publish_rabbitmq_message, так как это асинхронная функция.
# new_callable=AsyncMock гарантирует, что мок будет асинхронным.
@patch('game_server.tcp_handler.publish_rabbitmq_message', new_callable=AsyncMock)
class TestGameTCPHandlerRabbitMQ(unittest.IsolatedAsyncioTestCase):
    """
    Набор тестов для проверки взаимодействия TCP-обработчика игрового сервера с RabbitMQ.
    Проверяет, что команды, полученные от клиента, корректно публикуются в очередь RabbitMQ.
    """

    async def test_handle_game_client_shoot_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: команда SHOOT, полученная от клиента, публикуется в RabbitMQ.
        Имитирует успешную последовательность логина, затем команду SHOOT.
        Проверяет, что `publish_rabbitmq_message` вызывается с правильными аргументами.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader) # Мок для StreamReader
        mock_writer = AsyncMock(spec=asyncio.StreamWriter) # Мок для StreamWriter
        mock_writer.is_closing.return_value = False # Writer открыт
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345) # Адрес клиента
        
        # Имитируем последовательность команд от клиента: LOGIN, затем SHOOT, затем разрыв соединения
        login_command = "LOGIN test_user test_pass\n"
        shoot_command = "SHOOT\n"
        mock_reader.readuntil.side_effect = [ # Задаем последовательность возвращаемых значений для readuntil
            login_command.encode('utf-8'),  # Ответ на первый вызов (LOGIN)
            shoot_command.encode('utf-8'),  # Ответ на второй вызов (SHOOT)
            ConnectionResetError()          # Имитируем разрыв соединения для выхода из цикла в handle_game_client
        ]

        mock_game_room = MagicMock() # Мок для GameRoom
        # Мокируем authenticate_player для возврата успешного результата и мок-игрока
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Вход ОК", "token123")) # Сообщение на русском
        # Мокируем add_player
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() # Мок для remove_player, вызываемого в finally

        # Мокируем создание экземпляра Player внутри handle_game_client.
        # В этом тесте предполагается, что GameRoom возвращает уже аутентифицированный объект игрока,
        # или что Player создается внутри tcp_handler после успешной аутентификации.
        # Судя по структуре tcp_handler, Player создается после аутентификации.
        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance) as mock_player_class_constructor:
            await handle_game_client(mock_reader, mock_writer, mock_game_room) # Вызываем тестируемый обработчик

        # Ожидаемое сообщение для публикации в RabbitMQ
        expected_message_shoot = {
            "player_id": "test_user",
            "command": "shoot",
            "details": {"source": "tcp_handler"} # Дополнительная информация об источнике команды
        }
        # Проверяем, что publish_rabbitmq_message был вызван с командой SHOOT
        await asyncio.sleep(0) # Даем возможность выполниться асинхронным задачам (если они есть)
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_shoot) # Проверяем вызов
        
        # Проверяем, что клиенту было отправлено подтверждение получения команды (приблизительная проверка)
        await asyncio.sleep(0) # Снова даем время на выполнение задач
        # Собираем все данные, которые были записаны в writer
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"КОМАНДА_ПОЛУЧЕНА SHOOT\n", written_data, "Клиент не получил подтверждение команды SHOOT.")

    async def test_handle_game_client_move_command_publishes_to_rabbitmq(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: команда MOVE, полученная от клиента, публикуется в RabbitMQ.
        Имитирует успешный логин, затем команду MOVE с координатами.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        move_command = "MOVE 10 20\n" # Команда MOVE с координатами X=10, Y=20
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            move_command.encode('utf-8'),
            ConnectionResetError() # Для выхода из цикла
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Вход ОК", "token123")) # Сообщение на русском
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock()

        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        # Ожидаемое сообщение для RabbitMQ
        expected_message_move = {
            "player_id": "test_user",
            "command": "move",
            "details": {"new_position": [10, 20]} # Ожидаемые координаты
        }
        await asyncio.sleep(0) # Даем время на выполнение
        mock_publish_rabbitmq.assert_any_call('', 'player_commands', expected_message_move) # Проверяем вызов
        
        await asyncio.sleep(0) # Даем время на выполнение
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        self.assertIn(b"КОМАНДА_ПОЛУЧЕНА MOVE\n", written_data, "Клиент не получил подтверждение команды MOVE.")

    async def test_handle_game_client_unknown_command(self, mock_publish_rabbitmq: AsyncMock):
        """
        Тест: неизвестная команда от клиента не публикуется в RabbitMQ,
        и клиенту отправляется сообщение UNKNOWN_COMMAND.
        """
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)

        login_command = "LOGIN test_user test_pass\n"
        unknown_command = "JUMP\n" # Неизвестная команда
        mock_reader.readuntil.side_effect = [
            login_command.encode('utf-8'),
            unknown_command.encode('utf-8'),
            ConnectionResetError()
        ]
        mock_game_room = MagicMock()
        mock_player_instance = MockPlayer(mock_writer, name="test_user")
        mock_game_room.authenticate_player = AsyncMock(return_value=(True, "Вход ОК", "token123")) # Сообщение на русском
        mock_game_room.add_player = AsyncMock(return_value=mock_player_instance)
        mock_game_room.remove_player = AsyncMock() # Добавляем мок для remove_player
        
        with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
            await handle_game_client(mock_reader, mock_writer, mock_game_room)

        await asyncio.sleep(0) # Даем время
        # Проверяем, что publish_rabbitmq_message НЕ был вызван для неизвестной команды
        mock_publish_rabbitmq.assert_not_called() 
        
        await asyncio.sleep(0) # Даем время
        written_data = b"".join(arg[0][0] for arg in mock_writer.write.call_args_list if arg[0])
        # Проверяем, что было отправлено сообщение UNKNOWN_COMMAND
        self.assertIn(b"НЕИЗВЕСТНАЯ_КОМАНДА\n", written_data, "Клиент не получил сообщение UNKNOWN_COMMAND.")

if __name__ == '__main__':
    # Запуск тестов, если файл выполняется напрямую
    unittest.main()

# --- Тесты в стиле Pytest добавлены ниже ---
import pytest # Требуется для специфичных функций pytest, если не импортирован ранее
from game_server.game_logic import GameRoom # для мокирования типа (повторный импорт для ясности, если нужен)
from game_server.models import Player # для мокирования и проверки создания (повторный импорт для ясности, если нужен)
# CLIENT_TCP_READ_TIMEOUT может понадобиться, если тесты от него зависят, импортируется из handler.
# from game_server.tcp_handler import CLIENT_TCP_READ_TIMEOUT

@pytest.fixture
def mock_game_room_pytest(): # Переименовано, чтобы избежать конфликта, если фикстуры unittest и pytest находятся в одной глобальной области видимости
    room = MagicMock(spec=GameRoom)
    room.authenticate_player = AsyncMock()
    room.add_player = AsyncMock()
    room.remove_player = AsyncMock()
    room.handle_player_command = AsyncMock()
    return room

@pytest.fixture
def mock_reader_factory_pytest(): # Фабрика мок-ридеров
    def _factory(side_effects):
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readuntil.side_effect = side_effects
        return reader
    return _factory

@pytest.fixture
def mock_writer_pytest(): # Переименовано
    writer = AsyncMock(spec=asyncio.StreamWriter)
    writer.is_closing.return_value = False
    writer.get_extra_info.return_value = ('127.0.0.1', 12345)
    return writer

@pytest.mark.asyncio
async def test_handle_game_client_initial_ack_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест начального подтверждения подключения
    mock_reader = mock_reader_factory_pytest([asyncio.IncompleteReadError(b'', 0)])
    await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)
    mock_writer_pytest.write.assert_called_once_with(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n")
    assert mock_writer_pytest.close.call_count >= 1 # close может быть вызван в finally
    assert mock_writer_pytest.wait_closed.call_count >= 1


@pytest.mark.asyncio
async def test_handle_game_client_auth_success_then_disconnect_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест успешной аутентификации с последующим отключением
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN testuser password123\n",
        asyncio.IncompleteReadError(b'', 0)
    ])
    auth_msg = "Аутентификация успешна" # Сообщение на русском
    token = "test_token_123"
    mock_game_room_pytest.authenticate_player.return_value = (True, auth_msg, token)

    mock_player_instance = MagicMock(spec=Player)
    mock_player_instance.name = "testuser"
    mock_player_instance.id = 1
    mock_player_instance.writer = mock_writer_pytest

    with patch('game_server.tcp_handler.Player', return_value=mock_player_instance) as MockPlayerConstructor:
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once_with("testuser", "password123")

    expected_login_success_msg = f"ВХОД_УСПЕШЕН {auth_msg} Токен: {token}\n".encode('utf-8')
    calls = [call(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n"), call(expected_login_success_msg)]
    mock_writer_pytest.write.assert_has_calls(calls, any_order=False)

    MockPlayerConstructor.assert_called_once_with(writer=mock_writer_pytest, name="testuser", session_token=token)
    mock_game_room_pytest.add_player.assert_called_once_with(mock_player_instance)
    mock_game_room_pytest.remove_player.assert_called_once_with(mock_player_instance)

    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1

@pytest.mark.asyncio
async def test_handle_game_client_auth_failure_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест неудачной аутентификации
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN testuser password123\n",
        # Обработчик завершается после неудачной аутентификации, поэтому дальнейшие чтения для этого теста не нужны
    ])
    auth_msg = "Аутентификация не удалась" # Сообщение на русском
    mock_game_room_pytest.authenticate_player.return_value = (False, auth_msg, None)

    with patch('game_server.tcp_handler.Player') as MockPlayerConstructor:
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once_with("testuser", "password123")
    expected_login_failure_msg = f"ВХОД_НЕУДАЧА {auth_msg}\n".encode('utf-8')
    calls = [call(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n"), call(expected_login_failure_msg)]
    mock_writer_pytest.write.assert_has_calls(calls, any_order=False)

    MockPlayerConstructor.assert_not_called()
    mock_game_room_pytest.add_player.assert_not_called()
    mock_game_room_pytest.remove_player.assert_not_called()
    mock_writer_pytest.close.assert_called_once()
    mock_writer_pytest.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_handle_game_client_auth_exception_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест исключения при аутентификации
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN testuser password123\n",
    ])
    auth_exception_message = "Сервис аутентификации недоступен" # Сообщение на русском
    mock_game_room_pytest.authenticate_player.side_effect = Exception(auth_exception_message)

    with patch('game_server.tcp_handler.Player') as MockPlayerConstructor:
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once_with("testuser", "password123")
    expected_auth_exception_msg = f"КРИТИЧЕСКАЯ_ОШИБКА_СЕРВЕРА Exception\n".encode('utf-8') # Используется имя класса исключения
    calls = [call(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n"), call(expected_auth_exception_msg)]
    mock_writer_pytest.write.assert_has_calls(calls, any_order=False)

    MockPlayerConstructor.assert_not_called()
    mock_game_room_pytest.add_player.assert_not_called()
    mock_game_room_pytest.remove_player.assert_not_called()
    mock_writer_pytest.close.assert_called_once()
    mock_writer_pytest.wait_closed.assert_called_once()

@pytest.mark.asyncio
async def test_handle_game_client_command_processing_then_quit_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест обработки команд с последующим выходом
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN player_cmd superpass\n",
        b"SAY Hello\n",
        b"QUIT\n",
        asyncio.IncompleteReadError(b'', 0)
    ])
    mock_game_room_pytest.authenticate_player.return_value = (True, "Аутентификация успешна", "token1") # Сообщение на русском

    mock_player_instance = MagicMock(spec=Player)
    mock_player_instance.name = "player_cmd"
    mock_player_instance.id = 2
    mock_player_instance.writer = mock_writer_pytest

    with patch('game_server.tcp_handler.Player', return_value=mock_player_instance) as MockPlayerConstructor:
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once_with("player_cmd", "superpass")
    MockPlayerConstructor.assert_called_once_with(writer=mock_writer_pytest, name="player_cmd", session_token="token1")
    mock_game_room_pytest.add_player.assert_called_once_with(mock_player_instance)

    expected_command_calls = [call(mock_player_instance, "SAY Hello"), call(mock_player_instance, "QUIT")]
    mock_game_room_pytest.handle_player_command.assert_has_calls(expected_command_calls)

    mock_game_room_pytest.remove_player.assert_called_once_with(mock_player_instance)
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1

# --- Тесты в стиле Pytest для обработки ошибок и других команд ---
@pytest.mark.asyncio
async def test_handle_game_client_incomplete_read_username_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест неполного чтения имени пользователя
    mock_reader = mock_reader_factory_pytest([asyncio.IncompleteReadError(b'user', 4)])

    await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_writer_pytest.write.assert_called_once_with(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n")
    mock_game_room_pytest.authenticate_player.assert_not_called()
    assert mock_writer_pytest.close.call_count >= 1 # close может быть вызван в finally
    assert mock_writer_pytest.wait_closed.call_count >= 1


@pytest.mark.asyncio
async def test_handle_game_client_connection_reset_during_auth_read_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест сброса соединения во время чтения данных аутентификации
    # Попытка входа, затем сброс соединения при попытке чтения пароля
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN testuser \n", # Часть команды LOGIN
        ConnectionResetError("Connection reset while reading password") # Сброс соединения при чтении пароля
    ])
    # Примечание: Приведенный выше side_effect подразумевает, что "LOGIN user pass" находится на одной строке.
    # Если имя пользователя на одной строке, а пароль на другой, то это:
    # b"testuser\n", ConnectionResetError(...)
    # Для согласованности с предыдущими исправлениями предположим, что "LOGIN user pass" на одной строке.
    # Таким образом, если сброс происходит во время этой строки, это IncompleteReadError.
    # Если сброс происходит при *следующем* чтении (например, если LOGIN был просто "LOGIN\n", и сервер ожидает имя пользователя далее):
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN_CMD_EXPECTING_USER_PASS_LATER\n", # Пример, если сервер имеет многоэтапный вход
        ConnectionResetError("Connection reset")
    ])
    # Для этого теста предположим, что сервер ожидает "LOGIN user pass" на одной строке,
    # и сброс происходит *во время* чтения этой строки, вызывая IncompleteReadError.
    # Или, если сервер читает имя пользователя, а затем пароль отдельно:
    mock_reader = mock_reader_factory_pytest([
        b"testuser\n", # Имя пользователя успешно прочитано
        ConnectionResetError("Connection reset while reading password") # Сброс при чтении пароля
    ])
    # handle_game_client читает "LOGIN user pass" за один раз. Тест должен это отражать.
    # Сымитируем ConnectionResetError *вместо* IncompleteReadError для другого пути кода.
    # Это означает, что asyncio.open_connection не удается, или сам readuntil вызывает его, не обернутый в wait_for.
    # Текущий tcp_handler перехватывает ConnectionResetError в общем блоке try-except.

    # Переоценка: Тестируем ConnectionResetError после успешного ACK.
    # Первое readuntil предназначено для "LOGIN user pass". Если оно вызывает ConnectionResetError:
    mock_reader = mock_reader_factory_pytest([
        ConnectionResetError("Connection reset during login line read") # Сброс соединения во время чтения строки входа
    ])

    await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_writer_pytest.write.assert_called_once_with(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n")
    mock_game_room_pytest.authenticate_player.assert_not_called()
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1


@pytest.mark.asyncio
async def test_handle_game_client_timeout_reading_command_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест таймаута при чтении команды
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN timeout_user password\n",
        asyncio.TimeoutError # Таймаут при ожидании команды после входа
    ])
    mock_game_room_pytest.authenticate_player.return_value = (True, "Аутентификация успешна", "token_timeout") # Сообщение на русском
    mock_player_instance = MagicMock(spec=Player, id=3)
    mock_player_instance.name = "timeout_player"
    mock_player_instance.writer = mock_writer_pytest

    with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once_with("timeout_user", "password")
    mock_game_room_pytest.add_player.assert_called_once_with(mock_player_instance)
    mock_writer_pytest.write.assert_any_call(b"ОШИБКА_СЕРВЕРА Таймаут ожидания команды\n")
    mock_game_room_pytest.remove_player.assert_called_once_with(mock_player_instance)
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1

@pytest.mark.asyncio
async def test_handle_game_client_empty_command_after_login_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест пустой команды после входа
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN empty_cmd_user password\n",
        b"\n", # Пустая команда
        asyncio.IncompleteReadError(b'', 0)
    ])
    mock_game_room_pytest.authenticate_player.return_value = (True, "Аутентификация успешна", "token_empty_cmd") # Сообщение на русском
    mock_player_instance = MagicMock(spec=Player, id=4)
    mock_player_instance.name = "empty_cmd_user"
    mock_player_instance.writer = mock_writer_pytest

    with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once()
    mock_game_room_pytest.add_player.assert_called_once_with(mock_player_instance)
    mock_writer_pytest.write.assert_any_call(b"ПУСТАЯ_КОМАНДА\n")
    mock_game_room_pytest.handle_player_command.assert_not_called()
    mock_game_room_pytest.remove_player.assert_called_once_with(mock_player_instance)
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1

@pytest.mark.asyncio
async def test_handle_game_client_unknown_command_after_login_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест неизвестной команды после входа
    mock_reader = mock_reader_factory_pytest([
        b"LOGIN unknown_cmd_user password\n",
        b"BLABLA\n",
        asyncio.IncompleteReadError(b'', 0)
    ])
    mock_game_room_pytest.authenticate_player.return_value = (True, "Аутентификация успешна", "token_unknown_cmd") # Сообщение на русском
    mock_player_instance = MagicMock(spec=Player, id=5)
    mock_player_instance.name = "unknown_cmd_user"
    mock_player_instance.writer = mock_writer_pytest

    with patch('game_server.tcp_handler.Player', return_value=mock_player_instance):
        await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_called_once()
    mock_game_room_pytest.add_player.assert_called_once_with(mock_player_instance)
    mock_writer_pytest.write.assert_any_call(b"НЕИЗВЕСТНАЯ_КОМАНДА\n")
    mock_game_room_pytest.handle_player_command.assert_not_called()
    mock_game_room_pytest.remove_player.assert_called_once_with(mock_player_instance)
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1

@pytest.mark.asyncio
async def test_handle_game_client_register_command_pytest(mock_reader_factory_pytest, mock_writer_pytest, mock_game_room_pytest): # Тест команды REGISTER
    # Команда REGISTER обрабатывается до типичного цикла аутентификации
    mock_reader = mock_reader_factory_pytest([
        b"REGISTER newuser newpass\n",
        asyncio.IncompleteReadError(b'',0) # Для остановки после этой команды, иначе обработчик может завершиться
    ])

    await handle_game_client(mock_reader, mock_writer_pytest, mock_game_room_pytest)

    mock_game_room_pytest.authenticate_player.assert_not_called()
    calls = [
        call(b"СЕРВЕР_ПОДКЛЮЧЕНИЕ_ПОДТВЕРЖДЕНО\n"),
        call(b"РЕГИСТРАЦИЯ_НЕУДАЧА Регистрация через игровой сервер пока не поддерживается.\n")
    ]
    mock_writer_pytest.write.assert_has_calls(calls, any_order=False)
    mock_game_room_pytest.add_player.assert_not_called()
    mock_game_room_pytest.remove_player.assert_not_called()
    assert mock_writer_pytest.close.call_count >= 1
    assert mock_writer_pytest.wait_closed.call_count >= 1