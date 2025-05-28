# auth_server/tcp_handler.py
# Этот модуль отвечает за обработку TCP-соединений и сообщений от клиентов
# для сервера аутентификации.
import asyncio
import json # Импортируем json для работы с JSON-сообщениями
import logging # Импортируем logging для логирования
from .user_service import authenticate_user # Импортируем функцию аутентификации пользователя
from .metrics import ACTIVE_CONNECTIONS_AUTH, SUCCESSFUL_AUTHS, FAILED_AUTHS # Импортируем метрики Prometheus

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def handle_auth_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Обрабатывает входящее клиентское подключение для аутентификации.

    Читает данные от клиента, ожидает JSON-сообщение с действием (login/register),
    обрабатывает его и отправляет ответ. Обновляет метрики Prometheus.

    Args:
        reader: Объект asyncio.StreamReader для чтения данных от клиента.
        writer: Объект asyncio.StreamWriter для отправки данных клиенту.
    """
    addr = writer.get_extra_info('peername') # Получаем адрес клиента
    logger.info(f"Новое подключение от {addr}, ожидается JSON.")
    ACTIVE_CONNECTIONS_AUTH.inc() # Увеличиваем счетчик активных соединений
    response_data = {} # Инициализируем переменную для данных ответа

    try:
        # Читаем данные до символа новой строки. Ожидается, что клиент отправит JSON и \n.
        raw_data_bytes = await reader.readuntil(b'\n') 
        
        # Проверка на пустые данные или только символ новой строки перед декодированием
        if not raw_data_bytes.strip(): # MODIFIED - проверяем после strip(), чтобы учесть \n
            logger.warning(f"От {addr} получено пустое сообщение или только символ новой строки. Отправка ошибки и закрытие.")
            response_data = {"status": "error", "message": "Получено пустое сообщение или только символ новой строки"} # Error message updated
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции, finally выполнит очистку
            
        # Декодируем байты в строку UTF-8. Используем строгую проверку.
        raw_data = raw_data_bytes.decode('utf-8') 
        logger.debug(f"TCP Handler: Получена сырая строка от клиента {addr}: '{raw_data.strip()}'")
        
        # Удаляем пробельные символы с начала и конца строки.
        message_json_str = raw_data.strip()
        
        # Проверка, не является ли строка пустой ПОСЛЕ удаления пробельных символов.
        if not message_json_str: 
            logger.warning(f"От {addr} получено пустое сообщение после strip. Отправка ошибки и закрытие.")
            response_data = {"status": "error", "message": "Получено пустое сообщение"} # This specific error message
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции

        try:
            # message_json_str уже декодирована и очищена от пробелов.
            logger.debug(f"Получена строка JSON от {addr}: '{message_json_str}'")
            message_data = json.loads(message_json_str) # Парсим JSON-строку в Python dict
            logger.debug(f"TCP Handler: Распарсенный JSON от клиента {addr}: {message_data}")
            action = message_data.get("action") or message_data.get("command") # Получаем действие из сообщения
            username = message_data.get("username") # Получаем имя пользователя
            password = message_data.get("password") # Получаем пароль

            logger.info(f"Получен action '{action}' от {addr} для пользователя '{username}'")

            if action == "login": # Если действие - "login"
                is_authenticated, response_message = await authenticate_user(username, password)
                if is_authenticated:
                    SUCCESSFUL_AUTHS.inc() # Увеличиваем счетчик успешных аутентификаций
                    # Временно используем response_message (который является токеном или ID сессии) как session_id
                    response_data = {"status": "success", "message": response_message, "session_id": response_message} 
                    logger.info(f"Пользователь '{username}' успешно аутентифицирован. Ответ: {response_data}")
                else:
                    FAILED_AUTHS.inc() # Увеличиваем счетчик неудачных аутентификаций
                    response_data = {"status": "failure", "message": f"Аутентификация не удалась: {response_message}"}
                    logger.warning(f"Неудачная попытка аутентификации для пользователя '{username}'. Причина: {response_message}. Ответ: {response_data}")
            
            elif action == "register": # Если действие - "register"
                # Это mock-ответ для регистрации. В реальной системе здесь была бы логика регистрации.
                response_data = {"status": "success", "message": "Действие регистрации получено (mock-ответ)"}
                logger.info(f"Получен mock-запрос на регистрацию для пользователя '{username}'. Ответ: {response_data}")
            
            else: # Если действие неизвестно
                response_data = {"status": "error", "message": "Неизвестное или отсутствующее действие"}
                logger.warning(f"Неизвестное или отсутствующее действие '{action}' от {addr}. Ответ: {response_data}")

        # Обработка ошибки декодирования JSON.
        except json.JSONDecodeError as je:
            # message_json_str доступна здесь и содержит строку, вызвавшую ошибку.
            logger.error(f"От {addr} получен невалидный JSON: '{message_json_str}' | Ошибка: {je}. Сырые байты: {raw_data_bytes!r}")
            response_data = {"status": "error", "message": "Невалидный формат JSON"}
            # FAILED_AUTHS.inc() # Можно рассмотреть, считать ли это неудачной аутентификацией
            writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
            await writer.drain()
            # Явный блок закрытия удален, полагаемся на finally
            return # Выход из функции

        # Отправка успешного ответа клиенту (если не было ошибок выше)
        writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
        await writer.drain()
        logger.debug(f"Отправлен JSON ответ клиенту {addr}: {response_data}")
        # Явный блок закрытия удален, finally закроет соединение и уменьшит счетчик.
        # Нет return здесь, чтобы finally выполнился для ACTIVE_CONNECTIONS_AUTH.dec()

    except ConnectionResetError:
        logger.warning(f"Соединение сброшено клиентом {addr}.")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    except asyncio.IncompleteReadError:
        logger.warning(f"Неполное чтение от клиента {addr}. Соединение могло быть закрыто преждевременно.")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    # Убедимся, что UnicodeDecodeError перехватывается перед общим Exception,
    # если ошибка декодирования произойдет вне внутреннего try-except.
    except UnicodeDecodeError as ude: 
        logger.error(f"Ошибка декодирования Unicode от {addr} (внешний перехват): {ude}. Сырые данные: {raw_data_bytes!r}")
        response_data = {"status": "error", "message": "Неверная кодировка символов. Ожидается UTF-8."}
        
        # Этот лог остается для отладки состояния writer
        logger.debug(f"В обработчике UnicodeDecodeError для {addr}: writer.is_closing() равно {writer.is_closing()}") 
        
        if not writer.is_closing(): # Если writer еще не закрывается
            try:
                logger.debug(f"Попытка отправить ответ об ошибке UnicodeDecodeError клиенту {addr}")
                writer.write(json.dumps(response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"Успешно отправлен ответ об ошибке UnicodeDecodeError клиенту {addr}")
            except Exception as ex_send:
                logger.error(f"Не удалось отправить JSON сообщение об ошибке (UnicodeDecodeError) клиенту {addr}: {ex_send}")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции
    except Exception as e:
        # Логируем исключение с полным стектрейсом.
        logger.exception(f"Общая ошибка при обработке клиента {addr}:")
        # FAILED_AUTHS.inc() # Можно засчитать как неудачу, если ошибка произошла до успешной аутентификации
        
        if not writer.is_closing(): # Если writer еще не закрывается
            try:
                # Гарантируем, что даже при общих ошибках пытаемся отправить JSON-ответ.
                error_response_data = {"status": "error", "message": "Внутренняя ошибка сервера"}
                writer.write(json.dumps(error_response_data).encode('utf-8') + b'\n')
                await writer.drain()
                logger.debug(f"Отправлено JSON сообщение об ошибке клиенту {addr}: {error_response_data}")
            except Exception as ex_send:
                logger.error(f"Не удалось отправить JSON сообщение об ошибке клиенту {addr}: {ex_send}")
        # Явный блок закрытия удален, полагаемся на finally
        return # Выход из функции после обработки общего исключения
    finally:
        # Блок finally гарантирует, что ресурсы будут освобождены.
        logger.debug(f"Вход в блок finally для {addr}, подготовка к закрытию writer.")
        logger.info(f"Закрытие соединения с {addr}")
        ACTIVE_CONNECTIONS_AUTH.dec() # Уменьшаем счетчик активных соединений
        if not writer.is_closing(): # Проверяем, не закрывается ли writer уже
            logger.debug(f"Закрытие writer для {addr} в блоке finally.")
            writer.close() # Закрываем writer
            try:
                await writer.wait_closed() # Ожидаем полного закрытия
            except Exception as e_close:
                logger.error(f"Ошибка при ожидании закрытия writer для {addr}: {e_close}")
        logger.debug(f"Соединение с {addr} полностью закрыто.")
