# Серверная архитектура Tanks Blitz (Прототип)

Этот проект представляет собой прототип серверной архитектуры для многопользовательской игры Tanks Blitz, разработанный на Python.
Он включает компоненты для аутентификации, игровой логики, обработки команд через брокеры сообщений, масштабирования, мониторинга и резервного копирования.

## Обзор проекта

Цель проекта - продемонстрировать построение серверной части для MMO-игры с учетом современных практик и технологий, таких как:
- Разделение сервисов (аутентификация, игра)
- Асинхронное программирование и обработка событий
- Брокеры сообщений (Kafka, RabbitMQ) для асинхронных задач и логирования
- Паттерны проектирования (Singleton, Object Pool)
- Контейнеризация (Docker)
- Оркестрация (Kubernetes)
- Мониторинг (Prometheus, Grafana)
- Защита от DDoS (Nginx)
- Резервное копирование (Redis)

## Архитектура

Система состоит из следующих основных компонентов:

1.  **Клиент Игры** (не входит в этот репозиторий)
2.  **Nginx (Входная точка/Балансировщик/Защита от DDoS):**
    *   Принимает весь трафик от клиентов.
    *   Проксирует TCP-трафик на Сервер Аутентификации.
    *   Проксирует UDP-трафик на Игровой Сервер.
    *   Может быть настроен для базовой защиты от DDoS.
    *   Разворачивается в Kubernetes.
3.  **Сервер Аутентификации (Auth Server):**
    *   **Протокол: TCP, JSON.**
    *   Назначение: Регистрация и аутентификация. Отправляет события аудита в Kafka.
    *   Технологии: Python, `asyncio`, Kafka-клиент.
    *   Экспортирует метрики для Prometheus на порт `8000`.
4.  **Игровой Сервер (Game Server):**
    *   **Протокол: UDP (основной игровой), TCP (управляющие команды). Сообщения в формате JSON.**
    *   Назначение: Обработка игровой логики, синхронизация состояния игры. Взаимодействует с RabbitMQ для получения команд игроков и событий матчмейкинга. Отправляет события состояния игры и данные в Kafka.
    *   Паттерны: `SessionManager` (Singleton), `TankPool` (Object Pool).
    *   Компоненты:
        *   `udp_handler.py`, `tcp_handler.py`: Обработка входящих команд, публикация в RabbitMQ.
        *   `command_consumer.py`: Содержит `PlayerCommandConsumer` (обработка команд из RabbitMQ) и `MatchmakingEventConsumer` (обработка событий матчмейкинга из RabbitMQ).
        *   `session_manager.py`, `tank_pool.py`, `tank.py`: Основная игровая логика, отправка событий в Kafka.
    *   Технологии: Python, `asyncio`, Kafka-клиент, Pika (RabbitMQ-клиент).
    *   Экспортирует метрики для Prometheus на порт `8001`.
5.  **Kafka (Брокер сообщений):**
    *   Назначение: Сбор и хранение событий от различных компонентов системы для логирования, аналитики и потенциальной последующей обработки.
    *   Топики (основные): `player_sessions_history`, `tank_coordinates_history`, `game_events`, `auth_events`.
6.  **RabbitMQ (Брокер сообщений):**
    *   Назначение: Обработка асинхронных команд игроков и событий матчмейкинга.
    *   Очереди (основные): `player_commands`, `matchmaking_events`.
7.  **Redis:**
    *   Назначение: Кэширование, хранение временных данных сессий (если необходимо).
8.  **Prometheus:**
9.  **Grafana:**
10. **База данных (PostgreSQL - концептуально):**

### Обновленный Поток Команд и Событий

С внедрением Kafka и RabbitMQ поток обработки команд и логирования событий изменился:

1.  **Обработка Команд Игрока (например, "shoot", "move"):**
    *   Клиент игры отправляет команду (по TCP или UDP) на соответствующий обработчик Игрового Сервера (`tcp_handler.py` или `udp_handler.py`).
    *   Обработчик формирует сообщение команды и публикует его в очередь `player_commands` в RabbitMQ.
    *   `PlayerCommandConsumer` (в `game_server/command_consumer.py`) получает команду из очереди.
    *   Consumer вызывает соответствующий метод игровой логики (например, `tank.shoot()` или `tank.move()`).

2.  **Обработка Событий Матчмейкинга:**
    *   Предполагается, что внешний сервис матчмейкинга (не входит в этот прототип) публикует событие о создании нового матча (например, `new_match_created`) в очередь `matchmaking_events` в RabbitMQ.
    *   `MatchmakingEventConsumer` (в `game_server/command_consumer.py`) получает это событие.
    *   Consumer вызывает `SessionManager` для создания новой игровой сессии.

3.  **Логирование Событий и Данных в Kafka:**
    *   **События сессий:** `SessionManager` при создании сессии (`session_created`), удалении сессии (`session_removed`), присоединении игрока (`player_joined_session`) или выходе игрока (`player_left_session`) отправляет соответствующие события в топик `player_sessions_history` в Kafka.
    *   **Координаты танков:** Метод `tank.move()` после обновления позиции танка отправляет событие `tank_moved` с новыми координатами в топик `tank_coordinates_history` в Kafka.
    *   **Игровые события:** Методы класса `Tank` (например, `shoot()`, `take_damage()`) отправляют события `tank_shot`, `tank_took_damage`, `tank_destroyed` в топик `game_events` в Kafka.
    *   **События аутентификации:** Сервер аутентификации отправляет события (например, `user_logged_in`, `user_login_failed`) в топик `auth_events` в Kafka.

Эта архитектура с брокерами сообщений позволяет повысить отказоустойчивость, масштабируемость и гибкость системы, а также обеспечивает централизованное логирование для последующего анализа и построения аналитики.

### Структура проекта

- `auth_server/`: Код сервера аутентификации.
- `game_server/`: Код игрового сервера.
- `core/`: Общие модули.
- `tests/`: Юнит и нагрузочные тесты.
  - `unit/`: Юнит-тесты (`pytest`).

## Требования

- Python 3.9+
- Docker
- `docker-compose`
- `kubectl`
- `locust`
- `netcat` (`nc`) или `telnet`

## Настройка и запуск на Windows

Для работы с проектом на Windows рекомендуется следующая конфигурация и шаги:

### 1. Установка Docker Desktop

*   **Скачайте и установите Docker Desktop для Windows** с официального сайта Docker: [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
*   **Рекомендация WSL2:** При установке Docker Desktop выберите бэкенд WSL2.

### 2. Установка Git
*   Скачайте и установите Git с [https://git-scm.com/download/win](https://git-scm.com/download/win).

### 3. Клонирование репозитория
*   Откройте командную строку и выполните:
    ```bash
    git clone https://<URL_вашего_репозитория>.git
    cd <имя_папки_репозитория>
    ```

## Message Broker Setup (Kafka & RabbitMQ)

### Локальный запуск (Docker Compose)

Убедитесь, что Docker Desktop запущен.
Файл `docker-compose.yml` включает Kafka и RabbitMQ. Для запуска:
```bash
docker-compose up -d

Или только брокеры:

docker-compose up -d zookeeper kafka rabbitmq

    Zookeeper: zookeeper:2181 (в Docker сети)
    Kafka: kafka:9092 (в Docker сети), localhost:29092 (с хоста)
    RabbitMQ: rabbitmq:5672 (в Docker сети), http://localhost:15672 (UI, user/password)

Kubernetes

Используйте Helm-чарты для Kafka и RabbitMQ.
Environment Variables

    KAFKA_BOOTSTRAP_SERVERS: Адреса брокеров Kafka. По умолчанию: localhost:9092. Для Docker Compose: kafka:9092 или localhost:29092.
    RABBITMQ_HOST: Хост RabbitMQ. По умолчанию: localhost. Для Docker Compose: rabbitmq.

Установка зависимостей

pip install -r requirements.txt 

Локальный запуск серверов (для разработки)
Предварительная настройка Python на Windows

    Установите Python (отметьте "Add Python to PATH").
    Создайте и активируйте виртуальное окружение (python -m venv venv, затем .\venv\Scripts\Activate.ps1 или .\venv\Scripts\activate.bat).
    Установите зависимости (pip install -r requirements.txt).

Настройка переменных окружения на Windows (для локального запуска)

    PowerShell:

    $env:KAFKA_BOOTSTRAP_SERVERS="localhost:29092"
    $env:RABBITMQ_HOST="localhost"

    CMD:

    set KAFKA_BOOTSTRAP_SERVERS=localhost:29092
    set RABBITMQ_HOST=localhost

Убедитесь, что Kafka и RabbitMQ запущены.

Сервер аутентификации:

python -m auth_server.main

TCP: localhost:8888. Prometheus: http://localhost:8000/metrics.

Игровой сервер:

python -m game_server.main

UDP: localhost:9999. Prometheus: http://localhost:8001/metrics.

## Testing

### Unit Tests

Unit tests cover individual modules and components of the system to ensure their correctness in isolation. They are located in the `tests/unit/` directory.

To run all unit tests, use either of the following commands from the project root directory:

-   **Using pytest:**
    ```bash
    python -m pytest tests/unit/ -v -s
    ```
-   **Using unittest discovery:**
    ```bash
    python -m unittest discover tests/unit
    ```

### Integration Tests

Integration tests (`tests/test_integration.py`) are designed to check the interaction between the `auth_server` and `game_server` processes.

To run the integration tests:
```bash
python -m unittest tests/test_integration.py
```

**Mock Mode (Default for tests):**
By default, for these integration tests to run without requiring live external services (Redis, Kafka, RabbitMQ), the servers are configured to run in a "mock mode". This is achieved by the test script (`tests/test_integration.py`) automatically setting the environment variable `USE_MOCKS=true` for the server subprocesses it launches. In this mode, clients for Redis, Kafka, and RabbitMQ within the core modules (`core/redis_client.py`, `core/message_broker_clients.py`) are simulated using Python's `unittest.mock.MagicMock` and do not attempt to connect to actual service instances.

**Using Real Services (Optional):**
A `docker-compose.yml` file is provided to run real instances of dependencies (Redis, Kafka, Zookeeper, RabbitMQ). To start these services:
```bash
# It's recommended to check if docker-compose or docker compose is available
# docker-compose --version
# docker compose version
docker compose up -d redis-service kafka rabbitmq 
# or for older docker-compose:
# docker-compose up -d redis-service kafka rabbitmq
```
If you wish to test the servers against these real services, the `USE_MOCKS=true` environment variable setting should be removed or set to `false` within `tests/test_integration.py` before the server subprocesses are launched. Alternatively, you can run the servers manually outside the test script, configured with the appropriate environment variables pointing to the live services.

**Known Issues:**
-   **Game Server Integration Tests:** As of the latest test runs, some integration tests for the `game_server` (specifically `test_05` through `test_09`) are failing. This is due to a `TypeError: argument of type 'int' is not iterable` occurring within the `GameRoom` logic in `game_server/game_logic.py`. The root cause is that the `GameRoom` instance's `self.players` attribute is incorrectly an integer `0` instead of a dictionary `{}` at runtime. This is suspected to be due to the Python interpreter executing an older, cached version of `game_logic.py` within the subprocess, despite recent code corrections and cache cleaning attempts. This requires further local investigation to ensure the correct code version is consistently executed.
-   **Auth Server Integration Tests:** All integration tests for the `auth_server` (`test_01` to `test_04`) are currently passing, correctly utilizing the centralized `MOCK_USERS_DB` and JSON request/response formats.

### Запуск и отладка юнит-тестов

В проекте используется стандартная библиотека unittest для написания и запуска юнит-тестов. Файлы тестов находятся в директории tests/unit/.

Индивидуальный запуск тестов:

Для более детальной диагностики и отладки рекомендуется запускать тесты для конкретного файла напрямую. Это можно сделать из корневой директории проекта с помощью команды:

python -m unittest tests/unit/имя_файла_теста.py

Например:

python -m unittest tests/unit/test_tcp_handler_game.py

Такой подход позволяет увидеть вывод (включая логи) только от интересующего набора тестов, что упрощает анализ.

Особенности мокирования асинхронного кода:

При тестировании асинхронных компонентов, особенно тех, что взаимодействуют с сетевыми операциями (например, asyncio.StreamReader, asyncio.StreamWriter), могут возникнуть следующие нюансы:

    Завершение асинхронных задач: Некоторые асинхронные функции могут порождать фоновые задачи, которые не успевают завершиться до выполнения ассертов в тесте. Чтобы дать этим задачам шанс выполниться, можно использовать await asyncio.sleep(0) непосредственно перед проверками:

    # ... (код вызова тестируемой асинхронной функции)
    await handle_game_client(mock_reader, mock_writer, mock_game_room)
    await asyncio.sleep(0) # Даем время на выполнение всех запланированных задач
    mock_publish_rabbitmq.assert_any_call(...) 

    Мокирование asyncio.StreamWriter: При использовании unittest.mock.AsyncMock для имитации asyncio.StreamWriter, его метод is_closing() по умолчанию может возвращать не то значение, которое ожидает тестируемый код (например, если код проверяет writer.is_closing() в цикле). Чтобы избежать преждевременного выхода из циклов, можно явно задать возвращаемое значение:

    mock_writer = AsyncMock(spec=asyncio.StreamWriter)
    mock_writer.is_closing.return_value = False 

    Контролируемое завершение чтения из asyncio.StreamReader: При мокировании StreamReader.readuntil(), чтобы симулировать последовательность входящих данных и затем корректно завершить чтение (например, для выхода из цикла while True в обработчике), можно использовать ConnectionResetError() в качестве одного из значений side_effect:

    mock_reader.readuntil.side_effect = [
        b"LOGIN user pass\n", 
        b"SOME_COMMAND\n",
        ConnectionResetError() # Сигнализирует о "разрыве" соединения
    ]

    Это более надежный способ завершения, чем, например, asyncio.IncompleteReadError, так как он обычно обрабатывается в блоках except сетевого кода.

Особенности мокирования зависимостей при инициализации объекта (в setUp):

Если тестируемый объект при своей инициализации (например, в __init__) обращается к внешним зависимостям (например, пытается установить сетевое соединение), то стандартные декораторы @patch или @patch.object на тестовых методах не успеют сработать для конструктора. Чтобы предотвратить реальные вызовы во время создания объекта в setUp, можно использовать patcher.start() и addCleanup(patcher.stop):

class TestMyConsumer(unittest.TestCase):
    def setUp(self):
        # Патчим зависимость ДО создания экземпляра
        self.patcher_dependency = patch('path.to.dependency')
        self.mock_dependency_for_setup = self.patcher_dependency.start()
        self.addCleanup(self.patcher_dependency.stop) # Гарантирует остановку патча

        # Патчим метод самого класса (если он вызывается в __init__)
        # Используем БЕЗ autospec в setUp, чтобы избежать InvalidSpecError при повторном патчинге на методе
        self.patcher_method = patch.object(MyConsumerClass, '_internal_method_called_by_init')
        self.mock_internal_method_for_setup = self.patcher_method.start()
        self.addCleanup(self.patcher_method.stop)

        self.consumer = MyConsumerClass() # Теперь конструктор использует моки

    # На тестовых методах можно использовать свои декораторы @patch, 
    # они создадут отдельные моки для самого теста.
    @patch.object(MyConsumerClass, '_internal_method_called_by_init', autospec=True)
    @patch('path.to.dependency')
    def test_something(self, mock_dependency_for_test, mock_internal_method_for_test):
        # ...

В этом примере, autospec=True используется на декораторе метода для более строгих проверок, в то время как в setUp для patch.object он может быть опущен, если его задача - только "заглушить" метод на время инициализации.

Важно при отладке: Если вы сталкиваетесь с ошибками в тестах, которые не удается воспроизвести или понять по стандартным логам pytest или unittest, убедитесь, что:

    Кеш pytest очищен: Удалите папку .pytest_cache.
    Локальные изменения соответствуют репозиторию: Если вы работаете со мной или в команде, убедитесь, что анализируемый и изменяемый код актуален. В случае расхождений, может потребоваться ручная замена содержимого файла на версию, предложенную для исправления, чтобы гарантировать применение изменений.
    Логгирование настроено: Для вывода подробной информации из тестируемых модулей, убедитесь, что логгирование настроено на достаточный уровень (например, DEBUG или INFO) в ваших тестовых файлах или глобально:

    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s')

Дальнейшие улучшения и TODO

    ...
    Интеграция с системой матчмейкинга для отправки событий new_match_created в RabbitMQ.
    Разработка клиентов или сервисов, которые будут читать из Kafka для аналитики, мониторинга аномалий, и т.д.
    ...
