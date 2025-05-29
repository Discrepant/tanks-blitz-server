# game_server/udp_handler.py
"""
Обрабатывает UDP-датаграммы от игровых клиентов для основного игрового взаимодействия.

Этот модуль определяет класс `GameUDPProtocol`, который наследуется от
`asyncio.DatagramProtocol`. Он отвечает за получение, декодирование,
парсинг JSON-сообщений от клиентов, обработку игровых действий и отправку
ответов или подтверждений.

Ключевые используемые компоненты:
- `asyncio.DatagramProtocol`: Базовый класс для реализации UDP-протоколов.
- `SessionManager`: Управляет игровыми сессиями и состоянием игроков.
- `TankPool`: Управляет пулом объектов танков.
- `publish_rabbitmq_message`: Функция для отправки сообщений в RabbitMQ.

Основные обрабатываемые действия (actions):
- `join_game`: Присоединение игрока к игровой сессии.
- `move`: Перемещение танка игрока (команда публикуется в RabbitMQ).
- `shoot`: Выстрел танка игрока (команда публикуется в RabbitMQ).
- `leave_game`: Выход игрока из сессии.

Модуль также интегрирован с системой метрик Prometheus для отслеживания
количества полученных датаграмм и присоединившихся игроков.
"""
import asyncio
import json
import logging # Добавляем импорт для логирования
from typing import Optional
from .session_manager import SessionManager, GameSession # Менеджер игровых сессий и GameSession
from .tank_pool import TankPool # Пул объектов танков
from .metrics import TOTAL_DATAGRAMS_RECEIVED, TOTAL_PLAYERS_JOINED # Метрики Prometheus
# Добавлен импорт для публикации команд в RabbitMQ
from core.message_broker_clients import publish_rabbitmq_message, RABBITMQ_QUEUE_PLAYER_COMMANDS 

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

class GameUDPProtocol(asyncio.DatagramProtocol):
    """
    Протокол для обработки UDP-датаграмм игрового сервера.

    Этот класс реализует логику для асинхронной обработки входящих UDP-пакетов.
    Он использует `SessionManager` для управления сессиями игроков и `TankPool`
    для управления объектами танков. Команды, требующие сложной обработки или
    изменения состояния игры (например, 'move', 'shoot'), перенаправляются
    в RabbitMQ для дальнейшей обработки соответствующими потребителями.
    """
    def __init__(self):
        """
        Инициализирует протокол и его зависимости.

        При инициализации создаются или получаются экземпляры (предположительно Singleton)
        `SessionManager` и `TankPool`, которые используются для управления состоянием
        игровых сессий и танков соответственно.
        """
        super().__init__()
        self.session_manager = SessionManager() # Получаем экземпляр менеджера сессий
        self.tank_pool = TankPool() # Получаем экземпляр пула танков
        logger.info("GameUDPProtocol initialized.")

    def connection_made(self, transport: asyncio.DatagramTransport):
        """
        Вызывается при установке "соединения" (создании и настройке сокета).

        Сохраняет предоставленный объект `transport`, который используется для
        отправки данных обратно клиентам.

        Args:
            transport (asyncio.DatagramTransport): Объект транспорта,
                представляющий UDP-сокет.
        """
        self.transport = transport
        logger.info(f"UDP socket opened and listening on {transport.get_extra_info('sockname')}")

    def datagram_received(self, data: bytes, addr: tuple):
        """
        Вызывается при получении UDP-датаграммы от клиента.

        Это основной метод обработки входящих данных. Он выполняет следующие шаги:
        1.  Декодирует полученные байты в строку UTF-8.
        2.  Очищает строку от лишних пробелов и нулевых символов.
        3.  Парсит строку как JSON-сообщение.
        4.  Проверяет наличие обязательных полей `player_id` и `action`.
        5.  В зависимости от значения `action`, выполняет соответствующую логику:
            *   `join_game`: Обрабатывает присоединение игрока к сессии.
                Взаимодействует с `SessionManager` для поиска или создания сессии
                и с `TankPool` для выделения танка. Отправляет ответ клиенту
                о результате операции.
            *   `move`: Обрабатывает команду движения танка. Формирует сообщение
                для RabbitMQ, содержащее `player_id`, `command: "move"`,
                `tank_id` и `new_position`. Публикует это сообщение в очередь
                `RABBITMQ_QUEUE_PLAYER_COMMANDS`. Отправляет клиенту оптимистичное
                подтверждение `{"status": "received", "command": "MOVE"}`.
            *   `shoot`: Обрабатывает команду выстрела. Формирует сообщение
                для RabbitMQ, содержащее `player_id`, `command: "shoot"` и
                `tank_id`. Публикует это сообщение в очередь
                `RABBITMQ_QUEUE_PLAYER_COMMANDS`. Отправляет клиенту оптимистичное
                подтверждение `{"status": "received", "command": "SHOOT"}`.
            *   `leave_game`: Обрабатывает выход игрока из сессии.
                Взаимодействует с `SessionManager` для удаления игрока из сессии
                и с `TankPool` для возврата танка в пул. Отправляет ответ клиенту.
        6.  Обрабатывает различные ошибки: ошибки декодирования, невалидный JSON,
            неизвестные действия, отсутствие обязательных полей. В случае ошибок
            старается отправить клиенту JSON-сообщение об ошибке.
        7.  Обновляет метрику `TOTAL_DATAGRAMS_RECEIVED`.

        Ожидаемый формат JSON-сообщения от клиента:
        ```json
        {
            "action": "имя_действия",
            "player_id": "уникальный_id_игрока",
            // ... другие поля в зависимости от действия ...
            // например, для "move": "position": [x, y]
        }
        ```

        Args:
            data (bytes): Полученные байты данных от клиента.
            addr (tuple): Адрес клиента (IP-адрес, порт).
        """
        logger.info(f"UDP Handler: Raw request received from {addr}: {data!r}")
        TOTAL_DATAGRAMS_RECEIVED.inc() # Увеличиваем счетчик полученных датаграмм
        
        decoded_payload_str = None # Будет использована в логе исключения, если другие строки не установлены

        try:
            logger.debug(f"Raw bytes received from {addr}: {data!r}") # Лог исходных байтов

            # 1. Попытка декодирования (строгая проверка UTF-8)
            try:
                decoded_payload_str = data.decode('utf-8') 
                logger.info(f"UDP Handler: Decoded message from {addr}: {decoded_payload_str.strip()}")
            except UnicodeDecodeError as ude:
                logger.error(f"Unicode decode error from {addr}: {ude}. Raw data: {data!r}")
                # Отправка ошибки клиенту
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid character encoding. UTF-8 expected."}).encode('utf-8'), addr)
                return

            # 2. Удаление пробельных символов
            processed_payload_str = decoded_payload_str.strip()
            
            # 3. Удаление нулевых символов (если есть)
            if '\x00' in processed_payload_str:
                cleaned_payload_str = processed_payload_str.replace('\x00', '')
                # Логирование, только если были изменения
                if cleaned_payload_str != processed_payload_str:
                    logger.warning(f"Null bytes removed from data from {addr}. Original: '{processed_payload_str}', Cleaned: '{cleaned_payload_str}'")
                    processed_payload_str = cleaned_payload_str
            
            # 4. Проверка на пустоту после очистки
            if not processed_payload_str:
                logger.warning(f"Empty message after decoding, whitespace and null character cleaning from {addr}. Original string: '{decoded_payload_str}', Original bytes: {data!r}")
                self.transport.sendto(json.dumps({"status": "error", "message": "Empty JSON message"}).encode('utf-8'), addr)
                return

            logger.debug(f"Successfully decoded, cleaned (whitespace, nulls) message from {addr}: '{processed_payload_str}'")

            # 5. Попытка парсинга JSON
            try:
                message = json.loads(processed_payload_str) 
            except json.JSONDecodeError as jde:
                # Логирование строки, которая не смогла быть распарсена, и исходных байтов
                logger.error(f"Invalid JSON received from {addr}: '{processed_payload_str}' | Error: {jde}. Raw bytes: {data!r}")
                self.transport.sendto(json.dumps({"status":"error", "message":"Invalid JSON format"}).encode('utf-8'), addr)
                return
            
            # Логирование успешно распарсенного JSON-объекта
            logger.debug(f"Successfully parsed JSON from {addr}: {message}")

            # Основная логика обработки сообщения
            action = message.get("action") # Действие, которое клиент хочет выполнить
            player_id = message.get("player_id") # ID игрока

            # Проверка наличия player_id
            if not player_id: 
                logger.warning(f"Missing player_id in message from {addr}. Message: '{processed_payload_str}'. Ignoring.")
                # Для UDP можно не отправлять ошибку, если ответ не ожидается.
                return

            logger.info(f"Received action '{action}' from player '{player_id}' ({addr})")

            # Обработка действия 'join_game'
            if action == "join_game": 
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if not session: # Если игрок еще не в сессии
                    tank = self.tank_pool.acquire_tank() # Пытаемся получить танк из пула
                    if tank:
                        TOTAL_PLAYERS_JOINED.inc() # Увеличиваем метрику присоединившихся игроков
                        # Логика выбора или создания сессии
                        active_sessions_list = list(self.session_manager.sessions.values())
                        target_session = None
                        # Поиск существующей сессии с местом
                        for s_iter in active_sessions_list:
                            if s_iter.get_players_count() < 2: # Пример: максимум 2 игрока в сессии
                                target_session = s_iter
                                break
                        if not target_session: # Если нет подходящей сессии, создаем новую
                            target_session = self.session_manager.create_session()
                        
                        # Добавление игрока в сессию
                        self.session_manager.add_player_to_session(target_session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": target_session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                        logger.info(f"Player {player_id} joined session {target_session.session_id} with tank {tank.tank_id}")
                    else:
                        # Если нет свободных танков
                        response = {"status": "join_failed", "reason": "No free tanks available"}
                        logger.warning(f"Failed to join player {player_id}: no free tanks.")
                else: # Если игрок уже в сессии
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"Player {player_id} is already in session {session.session_id}.")
                
                # Отправка ответа клиенту
                if response: 
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Sent response for join_game to player {player_id} ({addr}): {response}")

            # Обработка действия 'move'
            elif action == "move": 
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id')
                        if tank_id:
                            position = message.get("position")
                            if position:
                                # Формирование сообщения для RabbitMQ
                                command_message = {
                                    "player_id": player_id,
                                    "command": "move", # Тип команды для потребителя
                                    "details": {
                                        "source": "udp_handler", # Источник команды
                                        "tank_id": tank_id,      # ID танка
                                        "new_position": position # Новая позиция
                                    }
                                }
                                try:
                                    # Публикация команды в RabbitMQ
                                    publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message)
                                    logger.info(f"Published 'move' command for player {player_id} (tank: {tank_id}, position: {position}) to RabbitMQ queue '{RABBITMQ_QUEUE_PLAYER_COMMANDS}'.")
                                    # Отправка оптимистичного подтверждения клиенту
                                    confirmation_payload = {"status": "received", "command": "MOVE"}
                                    self.transport.sendto(json.dumps(confirmation_payload).encode('utf-8'), addr)
                                    logger.info(f"Sent command reception confirmation for 'MOVE' to {addr} for player {player_id}")
                                except Exception as e:
                                    logger.error(f"Failed to publish 'move' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True)
                            else:
                                logger.warning(f"Missing 'position' in 'move' command from player {player_id} ({addr}).")
                        else:
                            logger.warning(f"tank_id not found for player {player_id} in session, cannot perform 'move'.")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'move'.")

            # Обработка действия 'shoot'
            elif action == "shoot": 
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id') 
                        if tank_id: 
                            # Формирование сообщения для RabbitMQ
                            command_message = {
                                "player_id": player_id,
                                "command": "shoot", # Тип команды для потребителя
                                "details": {
                                    "source": "udp_handler", 
                                    "tank_id": tank_id 
                                }
                            }
                            try:
                                # Публикация команды в RabbitMQ
                                publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message)
                                logger.info(f"Published 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ queue '{RABBITMQ_QUEUE_PLAYER_COMMANDS}'.")
                                # Отправка оптимистичного подтверждения клиенту
                                confirmation_payload = {"status": "received", "command": "SHOOT"}
                                self.transport.sendto(json.dumps(confirmation_payload).encode('utf-8'), addr)
                                logger.info(f"Sent command reception confirmation for 'SHOOT' to {addr} for player {player_id}")
                            except Exception as e:
                                logger.error(f"Failed to publish 'shoot' command for player {player_id} (tank: {tank_id}) to RabbitMQ: {e}", exc_info=True)
                                # Опционально: отправить ошибку клиенту или обработать повторную попытку.
                        else:
                            logger.warning(f"tank_id not found for player {player_id} in session, cannot perform 'shoot'.")
                else:
                    logger.warning(f"Player {player_id} not in session, cannot perform 'shoot'.")
            
            # Обработка действия 'leave_game'
            elif action == "leave_game": 
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        # Удаление игрока из сессии и возврат танка в пул
                        self.session_manager.remove_player_from_session(player_id) 
                        self.tank_pool.release_tank(tank_id) 
                        response = {"status": "left_game", "message": "You have left the game."} 
                        logger.info(f"Player {player_id} (Tank: {tank_id}) left the game. Tank returned to pool.")
                    # Проверка, была ли сессия удалена (если стала пустой)
                    if not self.session_manager.get_session(session.session_id):
                         logger.info(f"Session {session.session_id} was automatically deleted (became empty).")
                else: # Если игрок не найден в активной сессии
                    response = {"status": "not_in_game", "message": "You are not currently in a game."} 
                    logger.warning(f"Player {player_id} tried to leave game but was not found in an active session.")
                
                # Отправка ответа клиенту
                if response: 
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Sent response for leave_game to player {player_id} ({addr}): {response}")

            # Обработка неизвестного действия
            else: 
                logger.warning(f"Unknown action '{action}' from player {player_id} ({addr}). Message: {processed_payload_str}")
                response = {"status": "error", "message": "Unknown action"} 
                self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                logger.debug(f"Sent error response (Unknown action) to player {player_id} ({addr}): {response}")

        except Exception as e:
            # Общая обработка исключений на верхнем уровне
            # Используем processed_payload_str если доступно, иначе decoded_payload_str, иначе логгируем сырые данные
            msg_for_log = processed_payload_str if processed_payload_str is not None else \
                          (decoded_payload_str if decoded_payload_str is not None else f"Raw data: {data!r}")
            logger.exception(f"Error processing datagram from {addr} (Processed/decoded data before error: '{msg_for_log}'):")
            try:
                # Попытка отправить общее сообщение об ошибке клиенту
                self.transport.sendto(json.dumps({"status":"error", "message":f"Internal server error: {type(e).__name__}"}).encode('utf-8'), addr)
            except Exception as ex_send:
                logger.error(f"Failed to send error message to client {addr}: {ex_send}")

    def broadcast_to_session(self, session: GameSession, message_dict: dict, log_reason: str = ""):
        """
        Отправляет сообщение всем игрокам в указанной сессии.

        Этот метод используется для рассылки обновлений состояния игры или других
        событий всем участникам конкретной игровой сессии.

        Args:
            session (GameSession): Объект сессии, игрокам которой будет отправлено сообщение.
                                   Ожидается, что у сессии есть атрибут `players` (словарь)
                                   и `session_id` для логирования.
            message_dict (dict): Словарь с сообщением для отправки.
                                 Будет сериализован в JSON.
            log_reason (str, optional): Причина рассылки, добавляемая в лог для ясности.
                                        По умолчанию пустая строка.
        """
        if not session:
            logger.warning(f"Attempted to broadcast to a null session. Log reason: {log_reason}, Message: {message_dict}")
            return

        message_bytes = json.dumps(message_dict).encode('utf-8') # Убеждаемся, что используется UTF-8
        # Логируем само сообщение только на уровне DEBUG, чтобы избежать загромождения логов при частых обновлениях.
        logger.debug(f"Broadcasting message to session {session.session_id} ({log_reason}): {message_dict}")
        
        # Итерация по игрокам в сессии
        for player_id, player_info in session.players.items(): 
            player_addr = player_info.get('address') # Получаем адрес игрока
            if not player_addr:
                logger.warning(f"Player {player_id} in session {session.session_id} has no address. Cannot broadcast message.")
                continue
            try:
                self.transport.sendto(message_bytes, player_addr) # Отправка сообщения
                logger.debug(f"Message ({log_reason}) sent to player {player_id} at {player_addr}")
            except Exception as e:
                logger.error(f"Error broadcasting message to player {player_id} at {player_addr}: {e}")
    
    def connection_lost(self, exc: Optional[Exception]):
        """
        Вызывается при "потере соединения" (закрытии сокета).

        Для датаграммных протоколов, таких как UDP, это обычно означает, что сокет
        был закрыт локально. Это не связано с потерей соединения с конкретным
        клиентом, так как UDP является протоколом без установления соединения.

        Args:
            exc (Optional[Exception]): Исключение, вызвавшее закрытие сокета,
                                       или None, если сокет был закрыт без ошибок.
        """
        # Этот метод вызывается для некоторых "подключенных" UDP-сокетов, но не для обычных слушающих сокетов.
        # В нашем случае, create_datagram_endpoint создает слушающий сокет, он не "теряет" соединение сам по себе.
        # Однако, он может быть закрыт, например, при остановке сервера.
        if exc:
            logger.error(f"UDP socket closed with error: {exc}")
        else:
            logger.info("UDP socket closed.")
