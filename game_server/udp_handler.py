# game_server/udp_handler.py
# Этот модуль определяет класс GameUDPProtocol, который обрабатывает UDP-датаграммы
# от игровых клиентов. Используется для основного игрового взаимодействия,
# такого как движение, стрельба и обновление состояния игры.
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

    Отвечает за получение, декодирование, парсинг JSON-сообщений от клиентов,
    обработку игровых действий (присоединение, движение, стрельба, выход) и
    отправку ответов/обновлений состояния.
    """
    def __init__(self):
        """
        Инициализирует протокол, получая экземпляры SessionManager и TankPool.
        Предполагается, что SessionManager и TankPool реализованы как Singletons.
        """
        super().__init__()
        self.session_manager = SessionManager() # Получаем экземпляр менеджера сессий
        self.tank_pool = TankPool() # Получаем экземпляр пула танков
        logger.info("GameUDPProtocol инициализирован.")

    def connection_made(self, transport):
        """
        Вызывается при установке "соединения" (создании сокета).
        Сохраняет транспорт для последующей отправки данных.
        """
        self.transport = transport
        logger.info(f"UDP сокет открыт и слушает на {transport.get_extra_info('sockname')}")

    def datagram_received(self, data: bytes, addr: tuple):
        """
        Вызывается при получении UDP-датаграммы.

        Обрабатывает входящие данные: декодирует, парсит JSON, выполняет действия
        в зависимости от содержимого сообщения (например, 'join_game', 'move', 'shoot').
        Обновляет метрики и отправляет ответы клиентам или широковещательные сообщения.

        Args:
            data (bytes): Полученные байты данных.
            addr (tuple): Адрес отправителя (IP, порт).
        """
        TOTAL_DATAGRAMS_RECEIVED.inc() # Увеличиваем счетчик полученных датаграмм
        # logger.debug(f"Получены сырые байты: {data}") # Перемещено ниже, после первой попытки обработки

        decoded_payload_str = None # Будет использовано в логе исключения, если другие строки не установлены

        try:
            logger.debug(f"Получены сырые байты от {addr}: {data!r}") # Логируем исходные байты

            # 1. Попытка декодирования (строгая)
            try:
                decoded_payload_str = data.decode('utf-8') # Строгое декодирование UTF-8
                logger.info(f"UDP Handler: Декодированное сообщение от {addr}: {decoded_payload_str.strip()}")
            except UnicodeDecodeError as ude:
                logger.error(f"Ошибка декодирования Unicode от {addr}: {ude}. Сырые данные: {data!r}")
                # Отправляем ошибку клиенту
                self.transport.sendto(json.dumps({"status":"error", "message":"Неверная кодировка символов. Ожидается UTF-8."}).encode('utf-8'), addr)
                return

            # 2. Удаление пробельных символов
            processed_payload_str = decoded_payload_str.strip()
            
            # 3. Удаление нулевых символов (если есть)
            if '\x00' in processed_payload_str:
                cleaned_payload_str = processed_payload_str.replace('\x00', '')
                # Логируем, только если были изменения, и используем очищенную строку
                if cleaned_payload_str != processed_payload_str:
                    logger.warning(f"Удалены нулевые символы из данных от {addr}. Оригинал: '{processed_payload_str}', Очищено: '{cleaned_payload_str}'")
                    processed_payload_str = cleaned_payload_str
            
            # 4. Проверка на пустоту после очистки
            if not processed_payload_str:
                logger.warning(f"Пустое сообщение после декодирования, очистки пробелов и нулевых символов от {addr}. Исходная строка: '{decoded_payload_str}', Исходные байты: {data!r}")
                self.transport.sendto(json.dumps({"status": "error", "message": "Пустое JSON-сообщение"}).encode('utf-8'), addr)
                return

            logger.debug(f"Успешно декодировано, очищено (пробелы, нули) сообщение от {addr}: '{processed_payload_str}'")

            # 5. Попытка парсинга JSON
            try:
                message = json.loads(processed_payload_str) # Парсим JSON
            except json.JSONDecodeError as jde:
                # Логируем строку, которая не смогла быть распарсена, и исходные байты
                logger.error(f"Невалидный JSON получен от {addr}: '{processed_payload_str}' | Ошибка: {jde}. Сырые байты: {data!r}")
                self.transport.sendto(json.dumps({"status":"error", "message":"Невалидный формат JSON"}).encode('utf-8'), addr)
                return
            
            # Если парсинг успешен, логируем JSON-объект
            logger.debug(f"Успешно распарсен JSON от {addr}: {message}")

            # Основная логика обработки сообщения начинается здесь
            action = message.get("action") # Действие, которое хочет выполнить клиент
            player_id = message.get("player_id") # ID игрока

            if not player_id: # Если ID игрока отсутствует
                logger.warning(f"Отсутствует player_id в сообщении от {addr}. Сообщение: '{processed_payload_str}'. Игнорируется.")
                # Можно отправить ошибку, но для UDP это может быть излишне, если не ожидается ответ.
                return

            logger.info(f"Получено действие '{action}' от игрока '{player_id}' ({addr})")

            if action == "join_game": # Присоединение к игре
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if not session: # Если игрок еще не в сессии
                    tank = self.tank_pool.acquire_tank() # Пытаемся получить танк из пула
                    if tank:
                        TOTAL_PLAYERS_JOINED.inc() # Увеличиваем счетчик присоединившихся игроков
                        # Логика выбора или создания сессии
                        active_sessions_list = list(self.session_manager.sessions.values())
                        target_session = None
                        for s_iter in active_sessions_list:
                            if s_iter.get_players_count() < 2: # Пример: максимум 2 игрока в сессии
                                target_session = s_iter
                                break
                        if not target_session: # Если нет подходящей сессии, создаем новую
                            target_session = self.session_manager.create_session()
                        
                        self.session_manager.add_player_to_session(target_session.session_id, player_id, addr, tank)
                        response = {"status": "joined", "session_id": target_session.session_id, "tank_id": tank.tank_id, "initial_state": tank.get_state()}
                        logger.info(f"Игрок {player_id} присоединился к сессии {target_session.session_id} с танком {tank.tank_id}")
                    else:
                        response = {"status": "join_failed", "reason": "Нет свободных танков"}
                        logger.warning(f"Не удалось присоединить игрока {player_id}: нет свободных танков.")
                else: # Если игрок уже в сессии
                    response = {"status": "already_in_session", "session_id": session.session_id}
                    logger.info(f"Игрок {player_id} уже находится в сессии {session.session_id}.")
                
                if response: # Отправляем ответ клиенту
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Отправлен ответ для join_game игроку {player_id} ({addr}): {response}")

            elif action == "move": # Движение танка
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank = self.tank_pool.get_tank(player_data['tank_id'])
                        if tank:
                            new_position = message.get("position")
                            tank.move(tuple(new_position)) # Убеждаемся, что позиция - кортеж
                            logger.debug(f"Танк {tank.tank_id} игрока {player_id} перемещен в {new_position}")
                            # Готовим обновление состояния игры для рассылки
                            current_game_state = {"action": "game_update", "tanks": session.get_tanks_state()}
                            self.broadcast_to_session(session, current_game_state, f"обновление_игры для игрока {player_id}")
                else:
                    logger.warning(f"Игрок {player_id} не в сессии, не может выполнить 'move'.")

            elif action == "shoot": # Выстрел танка
                session = self.session_manager.get_session_by_player_id(player_id)
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data.get('tank_id') # Получаем ID танка из данных игрока
                        if tank_id: # Проверяем, существует ли ID танка
                            # Существование танка будет проверено потребителем. Нам нужен только player_id и команда.
                            command_message = {
                                "player_id": player_id,
                                "command": "shoot",
                                "details": {
                                    "source": "udp_handler", # Источник команды
                                    "tank_id": tank_id # Включаем ID танка, чтобы потребитель мог легко его найти
                                    # "timestamp": time.time() # Опционально: можно включить временную метку клиента, если доступна и релевантна
                                }
                            }
                            try:
                                # Используем обменник по умолчанию (пустая строка), ключ маршрутизации - имя очереди
                                publish_rabbitmq_message('', RABBITMQ_QUEUE_PLAYER_COMMANDS, command_message)
                                logger.info(f"Опубликована команда 'shoot' для игрока {player_id} (танк: {tank_id}) в очередь RabbitMQ '{RABBITMQ_QUEUE_PLAYER_COMMANDS}'.")
                            except Exception as e:
                                logger.error(f"Не удалось опубликовать команду 'shoot' для игрока {player_id} (танк: {tank_id}) в RabbitMQ: {e}", exc_info=True)
                                # Опционально: отправить ошибку обратно игроку или обработать повторную попытку.
                                # Пока просто логируем ошибку.

                            # Удален прямой вызов tank.shoot() и broadcast_to_session для события выстрела.
                            # Потребитель теперь отвечает за обработку команды и любые результирующие обновления/рассылки состояния игры.
                            # Оптимистичное обновление может быть отправлено здесь, если это необходимо, но задание предполагает, что потребитель это обрабатывает.
                            # Пример: self.transport.sendto(json.dumps({"status":"shoot_command_sent"}).encode('utf-8'), addr)
                        else:
                            logger.warning(f"Не найден tank_id для игрока {player_id} в сессии, не может выполнить 'shoot'.")
                else:
                    logger.warning(f"Игрок {player_id} не в сессии, не может выполнить 'shoot'.")
            
            elif action == "leave_game": # Выход из игры
                session = self.session_manager.get_session_by_player_id(player_id)
                response = None
                if session:
                    player_data = session.players.get(player_id)
                    if player_data:
                        tank_id = player_data['tank_id']
                        self.session_manager.remove_player_from_session(player_id) # Удаляем игрока из сессии
                        self.tank_pool.release_tank(tank_id) # Возвращаем танк в пул
                        response = {"status": "left_game", "message": "Вы покинули игру."}
                        logger.info(f"Игрок {player_id} (Танк: {tank_id}) покинул игру. Танк возвращен в пул.")
                    # Проверяем, не была ли сессия удалена (если стала пустой)
                    if not self.session_manager.get_session(session.session_id):
                         logger.info(f"Сессия {session.session_id} была автоматически удалена (стала пустой).")
                else: # Если игрок не найден в активной сессии
                    response = {"status": "not_in_game", "message": "Вы в данный момент не в игре."}
                    logger.warning(f"Игрок {player_id} пытался покинуть игру, но не был найден в активной сессии.")
                
                if response: # Отправляем ответ клиенту
                    self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                    logger.debug(f"Отправлен ответ для leave_game игроку {player_id} ({addr}): {response}")

            else: # Неизвестное действие
                logger.warning(f"Неизвестное действие '{action}' от игрока {player_id} ({addr}). Сообщение: {processed_payload_str}")
                response = {"status": "error", "message": "Неизвестное действие"}
                self.transport.sendto(json.dumps(response).encode('utf-8'), addr)
                logger.debug(f"Отправлен ответ об ошибке (Неизвестное действие) игроку {player_id} ({addr}): {response}")

        except Exception as e:
            # Используем processed_payload_str, если доступно, иначе decoded_payload_str, иначе логируем сырые данные
            msg_for_log = processed_payload_str if processed_payload_str is not None else \
                          (decoded_payload_str if decoded_payload_str is not None else f"Сырые данные: {data!r}")
            logger.exception(f"Ошибка обработки датаграммы от {addr} (Обработанные/декодированные данные перед ошибкой: '{msg_for_log}'):")
            try:
                # Пытаемся отправить общее сообщение об ошибке клиенту
                self.transport.sendto(json.dumps({"status":"error", "message":f"Внутренняя ошибка сервера: {type(e).__name__}"}).encode('utf-8'), addr)
            except Exception as ex_send:
                logger.error(f"Не удалось отправить сообщение об ошибке клиенту {addr}: {ex_send}")

    def broadcast_to_session(self, session: GameSession, message_dict: dict, log_reason: str = ""):
        """
        Отправляет сообщение всем игрокам в указанной сессии.

        Args:
            session (GameSession): Объект сессии, игрокам которой будет отправлено сообщение.
            message_dict (dict): Словарь с сообщением для отправки (будет сериализован в JSON).
            log_reason (str, optional): Причина рассылки для логирования.
        """
        message_bytes = json.dumps(message_dict).encode('utf-8') # Убеждаемся, что используется UTF-8
        # Логируем само сообщение только на DEBUG уровне, чтобы не засорять логи при частых обновлениях
        logger.debug(f"Широковещательное сообщение для сессии {session.session_id} ({log_reason}): {message_dict}")
        for player_id, player_info in session.players.items(): # Итерируемся по игрокам в сессии
            player_addr = player_info['address'] # Получаем адрес игрока
            try:
                self.transport.sendto(message_bytes, player_addr) # Отправляем сообщение
                logger.debug(f"Сообщение ({log_reason}) отправлено игроку {player_id} на {player_addr}")
            except Exception as e:
                logger.error(f"Ошибка при широковещательной отправке игроку {player_id} на {player_addr}: {e}")
    
    def connection_lost(self, exc: Optional[Exception]):
        """
        Вызывается, когда "соединение" потеряно.
        Для датаграммных протоколов это обычно означает, что сокет был закрыт.
        """
        # Этот метод вызывается для некоторых "связанных" UDP сокетов, но не для обычных.
        # В нашем случае create_datagram_endpoint создает слушающий сокет, он не "теряет" соединение сам по себе.
        if exc:
            logger.error(f"UDP сокет закрыт с ошибкой: {exc}")
        else:
            logger.info("UDP сокет закрыт.")
