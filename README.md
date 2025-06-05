# Tank Battle Game Server

This project is the backend server for a multiplayer tank battle game. It features a microservice architecture with components for authentication and game logic, supporting both Python and C++ implementations for different parts of the system.

## Table of Contents

- [Project Goals](#project-goals)
- [Architecture Overview](#architecture-overview)
- [Детальное Описание Сервисов](#детальное-описание-сервисов)
- [Directory Structure](#directory-structure)
- [Data Flows](#data-flows)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Contributing](#contributing)
- [Стабилизация Окружения и Улучшения Сборки](#стабилизация-окружения-и-улучшения-сборки)
- [Future Improvements](#future-improvements)

## Project Goals

*   **Создание масштабируемого и высокопроизводительного бэкенда:** Разработать серверную часть для многопользовательской игры в танковые сражения в реальном времени, способную выдерживать значительные нагрузки и обеспечивать минимальные задержки.
*   **Разделение на микросервисы:** Реализовать независимые сервисы для аутентификации пользователей и игровой логики, что упрощает разработку, тестирование, развертывание и масштабирование отдельных компонентов системы.
*   **Эффективное межсервисное взаимодействие с помощью gRPC:** Использовать gRPC для быстрой и надежной коммуникации между внутренними сервисами, например, между C++ TCP сервером аутентификации и Python gRPC сервисом аутентификации.
*   **Асинхронная обработка задач и потоковая передача событий:** Применять очереди сообщений, такие как Kafka (для потоковой передачи событий, например, истории сессий, игровых событий) и RabbitMQ (для асинхронной обработки команд игроков), для повышения отказоустойчивости и снижения связанности компонентов.
*   **Надежное хранение данных с Redis:** Использовать Redis в качестве быстрого и эффективного хранилища данных для пользовательских сессий, кеширования и другой оперативной информации, доступ к которому осуществляется из Python сервиса аутентификации.
*   **Поддержка контейнеризации и оркестрации:** Обеспечить возможность развертывания приложения с использованием Docker-контейнеров и управления ими с помощью Kubernetes для упрощения развертывания, масштабирования и управления в различных средах.
*   **Интеграция системы мониторинга:** Внедрить Prometheus для сбора и отображения метрик производительности и состояния различных компонентов системы, что помогает в своевременном обнаружении и диагностике проблем.
*   **Гибкость разработки и производительность с Python и C++:** Предложить реализации серверных компонентов как на Python (для скорости разработки и удобства), так и на C++ (для критически важных по производительности частей, таких как игровой сервер), чтобы сбалансировать скорость разработки и эффективность выполнения.
*   **Повышение отказоустойчивости и наблюдаемости:** Внедрение механизмов для обеспечения стабильной работы сервисов при сбоях (например, healthchecks, retry-механизмы) и сбор детальной информации (логи, метрики) для анализа и отладки.

## Architecture Overview

Система спроектирована как набор взаимодействующих микросервисов, обеспечивающих различные аспекты игры и аутентификации.

### Компоненты Системы (Краткий Обзор)

1.  **Nginx (Концептуально):**
    *   **Роль:** Выполняет функции основной входной точки для всего клиентского трафика, обеспечивает SSL-терминацию, балансировку нагрузки и проксирование запросов к соответствующим бэкенд-сервисам.
    *   **Взаимодействие:** Принимает весь внешний трафик от пользователей.

2.  **Сервис Аутентификации:** Состоит из двух частей:
    *   **C++ TCP Auth Server (`auth_server_cpp`):** Внешний TCP-интерфейс для клиентов; проксирует запросы аутентификации/регистрации на Python Auth gRPC Service.
    *   **Python Auth gRPC Service (`auth_server`):** Реализует основную логику аутентификации, управления пользователями и сессиями, используя Redis для хранения данных и Kafka для публикации событий.

3.  **Игровой Сервис (`game_server_cpp`):**
    *   **Роль:** Обрабатывает всю логику игрового процесса в реальном времени (движение, стрельба, игровые сессии).
    *   **Взаимодействие:** Общается с клиентами по TCP/UDP, использует RabbitMQ для очередей команд, Kafka для игровых событий и Python Auth gRPC Service для валидации сессий.

4.  **Брокеры Сообщений:**
    *   **Kafka:** Для потоковой передачи событий (аутентификация, игровые события, история сессий).
    *   **RabbitMQ:** Для асинхронной обработки команд игроков.

5.  **Хранилище Данных Redis:** Используется Python Auth gRPC Service для хранения данных пользователей и сессий.

6.  **Система Мониторинга:**
    *   **Prometheus:** Сбор метрик со всех сервисов.
    *   **Grafana:** Визуализация метрик из Prometheus.

### Диаграмма Архитектуры (Mermaid)

```mermaid
graph TD
    subgraph User Interaction
        UserClient[Игровой Клиент]
    end

    subgraph Gateway / Load Balancer
        Nginx[Nginx]
    end

    subgraph Authentication Service
        CppTCPAUTH[C++ TCP Auth Server]
        PythonAuthGRPC[Python Auth gRPC Service]
    end

    subgraph Game Logic Service
        CppGameServer[C++ Game Server / TCP & UDP Handlers]
        PlayerCommandHandler[C++ Player Command Consumer]
    end
    
    subgraph Message Brokers
        KafkaAuth[Kafka (auth_events)]
        KafkaGame[Kafka (game_events, session_history, tank_coords)]
        RabbitMQCommands[RabbitMQ (player_commands)]
    end

    subgraph Data Stores
        Redis[Redis (User Data, Sessions)]
    end

    subgraph Monitoring
        Prometheus[Prometheus]
        Grafana[Grafana]
    end

    UserClient -->|TCP/UDP Game Traffic, TCP Auth Traffic| Nginx
    Nginx -->|TCP Auth Traffic (Port 9000)| CppTCPAUTH
    Nginx -->|TCP Game Traffic (Port 8888)| CppGameServer
    Nginx -->|UDP Game Traffic (Port 8889)| CppGameServer

    CppTCPAUTH -->|gRPC: Authenticate/Register User| PythonAuthGRPC
    
    PythonAuthGRPC -->|CRUD: User Credentials, Session Tokens| Redis
    PythonAuthGRPC -->|Pub: Auth Events (user_registered, user_loggedin)| KafkaAuth

    CppGameServer -->|gRPC: Validate Session Token| PythonAuthGRPC
    CppGameServer -->|Pub: Player Command| RabbitMQCommands
    PlayerCommandHandler -.->|Sub: Reads Player Command| RabbitMQCommands
    PlayerCommandHandler -->|Exec: Apply Command to Game State| CppGameServer
    CppGameServer -->|Pub: Game Events, Session History, Tank Coordinates| KafkaGame
    
    Prometheus -->|Scrapes Metrics HTTP Endpoint| CppTCPAUTH
    Prometheus -->|Scrapes Metrics HTTP Endpoint| PythonAuthGRPC
    Prometheus -->|Scrapes Metrics HTTP Endpoint| CppGameServer
    Prometheus -->|Scrapes Metrics (e.g., JMX Exporter)| KafkaGame
    Prometheus -->|Scrapes Metrics (e.g., RabbitMQ Exporter)| RabbitMQCommands
    Grafana -->|Queries Metrics| Prometheus
```

## Детальное Описание Сервисов

### Сервис Аутентификации

Сервис аутентификации отвечает за проверку учетных данных пользователей, регистрацию новых пользователей и управление сессиями. Он состоит из двух основных компонентов: внешнего C++ TCP сервера, принимающего запросы от клиентов, и внутреннего Python gRPC сервиса, реализующего основную бизнес-логику.

#### 1. Python Auth gRPC Service (`auth_server`)

*   **Назначение и роль**:
    *   Центральный компонент для всей логики, связанной с пользователями: создание учетных записей, проверка паролей, генерация и валидация сессионных токенов.
    *   Предоставляет gRPC интерфейс для других сервисов (в частности, для `auth_server_cpp` и `game_server_cpp`).
*   **Ключевые технологии и библиотеки**:
    *   Python 3.9 (согласно `auth_server/Dockerfile`)
    *   `grpcio`, `grpcio-tools`: для реализации gRPC сервера.
    *   `redis` (в `user_service.py` используется mock-база, но планируется Redis): для взаимодействия с Redis (хранение данных пользователей и сессий).
    *   `confluent-kafka` (планируется, судя по переменным окружения в `docker-compose.yml`): для асинхронной отправки событий аутентификации в Kafka.
    *   `passlib[bcrypt]`: для хеширования паролей (используется в `auth_grpc_server.py` при регистрации).
    *   `asyncio`: для асинхронной обработки gRPC запросов.
*   **API (gRPC)**:
    *   Определен в `protos/auth_service.proto`.
    *   **`AuthService`**:
        *   `rpc AuthenticateUser(AuthRequest) returns (AuthResponse)`:
            *   Принимает: `AuthRequest { string username; string password; }`
            *   Возвращает: `AuthResponse { bool authenticated; string message; string token; }`
            *   Логика: В `auth_grpc_server.py` вызывает `user_service.authenticate_user`. В текущей mock-реализации `user_service.py` сравнивает пароли как есть. В случае успеха, в качестве токена используется имя пользователя.
        *   `rpc RegisterUser(AuthRequest) returns (AuthResponse)`:
            *   Принимает: `AuthRequest { string username; string password; }`
            *   Возвращает: `AuthResponse { bool authenticated; string message; string token; }` (поле `authenticated` здесь обычно `false`, `token` пустой).
            *   Логика: В `auth_grpc_server.py` хеширует пароль с использованием `pbkdf2_sha256` и вызывает `user_service.create_user` (который в `user_service.py` является реализацией регистрации), сохраняя хеш в MOCK_USERS_DB.
*   **Конфигурационные параметры** (из `docker-compose.yml` и кода):
    *   `REDIS_HOST`: Хост Redis (переменная окружения).
    *   `REDIS_PORT`: Порт Redis (переменная окружения).
    *   `KAFKA_BOOTSTRAP_SERVERS`: Адреса брокеров Kafka (переменная окружения).
    *   Порт gRPC сервера: `50051` (захардкожен в `auth_grpc_server.py` и указан в `docker-compose.yml`).
*   **Взаимодействие с другими сервисами**:
    *   **Redis** (планируется): Хранение учетных данных пользователей и активных сессионных токенов. `user_service.py` содержит заглушку `initialize_redis_client`.
    *   **Kafka** (планируется): Публикация событий аутентификации.
    *   **C++ TCP Auth Server (`auth_server_cpp`)**: Принимает от него gRPC запросы.
    *   **C++ Game Server (`game_server_cpp`)**: Принимает от него gRPC запросы на валидацию сессий.
*   **Основная логика работы (текущая с mock-базой)**:
    *   **Регистрация**: `auth_grpc_server.py` получает логин/пароль, хеширует пароль (`pbkdf2_sha256`), вызывает `user_service.create_user`, который добавляет пользователя и хеш в `MOCK_USERS_DB`.
    *   **Аутентификация**: `auth_grpc_server.py` получает логин/пароль (сырой), вызывает `user_service.authenticate_user`, который сравнивает сырой пароль с паролем из `MOCK_USERS_DB`.
*   **Dockerfile**: `auth_server/Dockerfile`. Использует `python:3.9-slim-buster`. Устанавливает зависимости из `requirements.txt`. Копирует код `auth_server` и `protos`.
*   **Точка входа**: `auth_server.auth_grpc_server` (запускается через `python -m`).

#### 2. C++ TCP Auth Server (`auth_server_cpp`)

*   **Назначение и роль**:
    *   Внешний интерфейс для игровых клиентов, обрабатывающий первичные TCP-соединения для запросов на регистрацию и вход.
    *   Действует как проксирующий слой, транслируя запросы клиентов в gRPC-вызовы к Python Auth gRPC Service.
*   **Ключевые технологии и библиотеки**:
    *   C++17
    *   Boost.Asio: для реализации асинхронного TCP сервера.
    *   `grpc++` (libgrpc++): для взаимодействия с Python Auth gRPC сервисом.
    *   `nlohmann/json`: для парсинга JSON-запросов от клиентов и формирования JSON-ответов.
    *   CMake: для сборки проекта.
*   **API и протоколы**:
    *   **TCP (клиентский интерфейс)**: Слушает на порту, указанном при запуске (по умолчанию `9000` из `main_auth.cpp`, или через аргумент `--port` в `docker-compose.yml`).
        *   Принимает JSON-сообщения от клиентов. Ожидаемый формат:
            *   Общий: `{"action": "<action_name>", ...}`
            *   Логин: `{"action": "login", "username": "user1", "password": "password123"}`
            *   Регистрация: `{"action": "register", "username": "newuser", "password": "newpassword"}`
    *   **gRPC (клиент к `auth_server`)**: Использует сгенерированные из `protos/auth_service.proto` стабы (`auth::AuthService::Stub`) для вызова методов `AuthenticateUser` и `RegisterUser` на Python Auth gRPC сервисе.
*   **Конфигурационные параметры** (из `docker-compose.yml` и `main_auth.cpp`):
    *   `--port`: Порт TCP сервера (например, `9000`).
    *   `--grpc_addr`: Адрес Python Auth gRPC сервиса (например, `auth_server:50051`).
*   **Взаимодействие с другими сервисами**:
    *   **Python Auth gRPC Service**: Отправляет ему gRPC запросы `AuthenticateUser` и `RegisterUser`, получает `AuthResponse`.
    *   **Игровые клиенты**: Общается по TCP, обмениваясь JSON-сообщениями.
*   **Основная логика работы**:
    *   `AuthTcpServer` (`auth_tcp_server.cpp`) инициализирует acceptor Boost.Asio и ожидает новые TCP-соединения.
    *   Для каждого нового соединения создается объект `AuthTcpSession` (`auth_tcp_session.cpp`).
    *   `AuthTcpSession` асинхронно читает данные из сокета, накапливая их в `boost::asio::streambuf` до получения разделителя (например, `\n`).
    *   Полученные данные парсятся как JSON. Извлекается поле `action`.
    *   В зависимости от `action` ("login" или "register"), создается соответствующий `AuthRequest` для gRPC.
    *   Выполняется соответствующий gRPC вызов к Python Auth gRPC Service.
    *   Ответ gRPC (`AuthResponse`) преобразуется обратно в JSON и отправляется клиенту по TCP.
*   **Dockerfile и Сборка**:
    *   Собирается с помощью `cpp/Dockerfile` (общий для C++ сервисов).
    *   CMake-скрипт: `auth_server_cpp/CMakeLists.txt`.
    *   Зависит от библиотеки `proto_lib` (содержащей сгенерированный gRPC код из `auth_service.proto`), Boost.Asio, nlohmann/json, Threads, gRPC++.
*   **Точка входа**: `main_auth.cpp` создает и запускает `AuthTcpServer`.

#### 3. C++ Game Server (`game_server_cpp`)

*   **Назначение и роль**:
    *   Основной сервер, отвечающий за всю игровую логику, обработку действий игроков в реальном времени, управление состоянием игры и взаимодействие с клиентами.
    *   Реализован на C++ для достижения высокой производительности и низких задержек.
*   **Ключевые технологии и библиотеки**:
    *   C++17
    *   Boost.Asio: для асинхронной обработки сетевых соединений (TCP и UDP).
    *   `librdkafka` (C++ wrapper `librdkafka++`): для взаимодействия с Kafka (публикация игровых событий).
    *   `librabbitmq-c`: для взаимодействия с RabbitMQ (получение команд игроков).
    *   `nlohmann/json`: для сериализации/десериализации сообщений и состояний.
    *   `grpc++`: для gRPC-клиента к сервису аутентификации (валидация токенов).
    *   CMake: для сборки проекта.
*   **Сетевое взаимодействие**:
    *   **TCP (`tcp_handler.h/cpp`, `tcp_session.h/cpp`)**:
        *   Слушает на порту, указанном при запуске (например, `8888` через `--tcp_port`).
        *   Используется для управляющих команд, требующих надежной доставки: логин игрока в игровой мир, команды чата.
        *   Каждое TCP-соединение управляется экземпляром `GameTCPSession`.
    *   **UDP (`udp_handler.h/cpp`)**:
        *   Слушает на порту, указанном при запуске (например, `8889` через `--udp_port`).
        *   Используется для частых обновлений состояния игры: команды движения, стрельбы.
        *   Формат сообщений – JSON.
*   **Обработка команд игрока (`command_consumer.h/cpp`)**:
    *   Команды, полученные через TCP или UDP обработчики (например, "move", "shoot"), публикуются в очередь `player_commands` в RabbitMQ.
    *   `PlayerCommandConsumer` (отдельный поток) читает команды из этой очереди, находит сессию/танк игрока и применяет команду.
*   **Управление игровыми сессиями и объектами**:
    *   **`SessionManager` (`session_manager.h/cpp`)**: Синглет, управляет игровыми сессиями. Создает, предоставляет доступ, добавляет/удаляет игроков. Использует `find_or_create_session_for_player` для распределения игроков.
    *   **`GameSession` (`game_session.h/cpp`)**: Представляет игровую сессию. Содержит игроков и их танки, информацию о сессии.
    *   **`TankPool` (`tank_pool.h/cpp`)**: Синглет, управляет пулом танков. Предоставляет `acquire_tank()` и `release_tank()`.
    *   **`Tank` (`tank.h/cpp`)**: Игровой объект танка с состоянием (ID, позиция, здоровье, активность) и методами действий (`move`, `shoot`, `take_damage`).
*   **Взаимодействие с Kafka (`kafka_producer_handler.h/cpp`)**:
    *   Использует `KafkaProducerHandler` для отправки событий.
    *   Топики: `player_sessions_history` (события сессий), `tank_coordinates_history` (движение), `game_events` (выстрелы, урон, уничтожение и т.д.).
*   **Взаимодействие с сервисом Аутентификации**:
    *   `GameTCPSession` при логине может валидировать сессионный токен через gRPC-вызов к Python Auth gRPC сервису.
*   **Конфигурационные параметры** (аргументы командной строки из `main.cpp`):
    *   `--tcp_port` (порт TCP, по умолчанию `8888`)
    *   `--udp_port` (порт UDP, по умолчанию `8889`)
    *   `--rmq_host`, `--rmq_port`, `--rmq_user`, `--rmq_pass` (параметры RabbitMQ)
    *   `--kafka_brokers` (адреса Kafka, по умолчанию `kafka:19092` в коде, но `kafka:9092` в `docker-compose.yml`)
    *   `--auth_grpc_host`, `--auth_grpc_port` (адрес сервиса аутентификации)
*   **Dockerfile и Сборка**:
    *   Собирается через `cpp/Dockerfile`. Компоненты собираются в библиотеку `game_logic_lib`, которая линкуется с `game_server_app`.
*   **Точка входа**: `main.cpp` инициализирует все компоненты и запускает `io_context`.

### 4. Инфраструктурные Компоненты

#### Kafka

*   **Назначение и роль**:
    *   Используется как распределенная платформа для потоковой передачи событий в реальном времени. Основное применение - сбор и доставка логов, событий аудита, истории игровых сессий и других типов данных, которые могут обрабатываться различными потребителями асинхронно.
    *   Позволяет отделить генерацию событий от их немедленной обработки, повышая отказоустойчивость и масштабируемость системы.
*   **Ключевые технологии**: Apache Kafka (используется образ `confluentinc/cp-kafka`). Зависит от Zookeeper для координации.
*   **Основные топики** (на основе анализа кода и предыдущих описаний):
    *   `auth_events`: Публикуются Python Auth gRPC сервисом. Содержат события, связанные с аутентификацией пользователей (например, `user_registered`, `user_loggedin`).
    *   `game_events`: Публикуются C++ Game Server. Содержат события, связанные непосредственно с игровым процессом (например, `tank_shot`, `tank_took_damage`, `tank_destroyed`, `tank_activated`, `tank_deactivated`, `tank_reset`).
    *   `player_sessions_history`: Публикуются C++ Game Server (через `SessionManager`). Содержат события жизненного цикла игровых сессий (например, `session_created`, `session_removed`, `player_joined_session`, `player_left_session`).
    *   `tank_coordinates_history`: Публикуются C++ Game Server (через `Tank::move`). Записывают историю изменения координат танков.
*   **Формат сообщений**: Сообщения в Kafka обычно отправляются в формате JSON. Структура зависит от типа события.
*   **Конфигурация** (из `docker-compose.yml`):
    *   `KAFKA_BROKER_ID: 1`
    *   `KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181`
    *   `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT`
    *   `KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:29092`
    *   `KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,PLAINTEXT_HOST://0.0.0.0:29092`
    *   `KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT`
    *   `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1`
    *   `KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0`
*   **Клиенты**:
    *   C++: `librdkafka++` (используется через `KafkaProducerHandler`).
    *   Python: `confluent-kafka` (планируется для `auth_server`).

#### RabbitMQ

*   **Назначение и роль**:
    *   Используется как традиционный брокер сообщений для асинхронной обработки команд и задач, где важна гарантированная доставка и гибкая маршрутизация.
    *   В данном проекте основное применение - передача команд от игроков, полученных сетевыми обработчиками игрового сервера, к компоненту, отвечающему за их исполнение.
*   **Ключевые технологии**: RabbitMQ (используется образ `rabbitmq:3.12-management-alpine`).
*   **Основные очереди** (на основе анализа кода):
    *   `player_commands`: Используется C++ Game Server. TCP и UDP обработчики публикуют сюда команды игроков (движение, стрельба). `PlayerCommandConsumer` читает из этой очереди. Сообщения персистентные.
    *   `game_chat_messages`: Используется C++ Game Server (`GameTCPSession`) для публикации сообщений чата.
*   **Формат сообщений**: JSON.
*   **Конфигурация** (из `docker-compose.yml`):
    *   `RABBITMQ_DEFAULT_USER: user`
    *   `RABBITMQ_DEFAULT_PASS: password`
    *   Порты: `5672` (AMQP), `15672` (менеджмент-плагин).
*   **Клиенты**:
    *   C++: `librabbitmq-c` (используется в `PlayerCommandConsumer`, `GameUDPHandler`, `GameTCPSession`).

#### Redis

*   **Назначение и роль**:
    *   Быстрое in-memory хранилище данных типа "ключ-значение".
    *   Основное использование - хранение данных пользователей (учетные записи, хеши паролей) и информации об активных сессиях (сессионные токены) для Python Auth gRPC Service.
    *   Может также использоваться для кеширования.
*   **Ключевые технологии**: Redis (используется образ `redis:7-alpine`).
*   **Структура данных** (предполагаемая):
    *   Пользователи: ключи вида `user:<username>` или `user:<user_id>` (JSON-строки или Hash).
    *   Сессии: ключи вида `session:<token>` (со значением `user_id` и временем жизни).
*   **Конфигурация** (из `docker-compose.yml`):
    *   Порт: `6379`.
    *   Python Auth gRPC Service использует переменные окружения `REDIS_HOST` и `REDIS_PORT`.
*   **Клиенты**:
    *   Python: `redis` (asyncio-совместимая версия для `user_service.py`).

#### Prometheus & Grafana

*   **Prometheus**:
    *   **Назначение**: Сбор и хранение метрик системы.
    *   **Конфигурация**: `monitoring/prometheus/prometheus.yml`. Настроен на сбор метрик с C++ серверов и Python Auth gRPC сервиса (предполагается, что они предоставляют эндпоинты для метрик).
    *   **Порт**: `9090`.
*   **Grafana**:
    *   **Назначение**: Визуализация метрик из Prometheus, создание дашбордов.
    *   **Конфигурация**: Подключается к Prometheus.
    *   **Порт**: `3000`.
    *   **Данные**: Volume `grafana_data`.

#### Nginx (Концептуально)

*   **Назначение и роль**: Обратный прокси, балансировщик нагрузки, входная точка трафика.
*   **Предполагаемые функции**: SSL-терминация, проксирование на `cpp_auth_server` (TCP) и `cpp_game_server` (TCP/UDP).
*   **Конфигурация**: Пример в `deployment/nginx/nginx.conf`. В `docker-compose.yml` не развернут.

## Directory Structure

*   `auth_server/`: Исходный код Python-сервиса аутентификации (gRPC). Включает логику работы с пользователями, сессиями, Redis и Kafka.
    *   `auth_grpc_server.py`: Основной скрипт запуска gRPC сервера.
    *   `user_service.py`: Модуль для работы с данными пользователей в Redis.
    *   `session_store.py`: Модуль для управления сессиями в Redis.
    *   `Dockerfile`: Dockerfile для сборки образа Python Auth gRPC сервиса.
*   `auth_server_cpp/`: Исходный код C++ TCP-сервера аутентификации. Принимает запросы от клиентов и проксирует их к Python Auth gRPC сервису.
    *   `main_auth.cpp`: Точка входа для C++ TCP сервера аутентификации.
    *   `auth_tcp_server.h/cpp`: Логика TCP сервера.
    *   `auth_tcp_session.h/cpp`: Логика обработки индивидуальной TCP сессии клиента.
    *   `CMakeLists.txt`: Сборочный скрипт для этого компонента.
*   `core/`: Общие модули Python, используемые различными сервисами.
    *   `config.py`: Конфигурационные параметры.
    *   `message_broker_clients.py`: Клиенты для Kafka и RabbitMQ.
    *   `redis_client.py`: Клиент для Redis.
*   `cpp/`: Корневая директория для всех C++ компонентов и общих CMake-скриптов.
    *   `protos/`: Содержит `.proto` файлы и CMake-скрипт для генерации gRPC и Protobuf кода для C++ и Python.
    *   `game_server_cpp/`: Исходный код C++ игрового сервера (TCP/UDP обработчики, логика игры, обработчик команд).
    *   `auth_server_cpp/`: (см. выше)
    *   `tests/`: Юнит-тесты для C++ компонентов.
    *   `CMakeLists.txt`: Корневой CMake-файл для сборки всех C++ проектов.
    *   `Dockerfile`: Dockerfile для сборки C++ сервисов и их зависимостей.
*   `deployment/`: Файлы, связанные с развертыванием (например, `docker-compose.yml`, конфигурации Kubernetes).
*   `game_server_cpp/`: Исходный код C++ игрового сервера.
    *   `main.cpp`: Точка входа для C++ игрового сервера.
    *   `udp_handler.h/cpp`: Логика UDP обработчика.
    *   `tcp_handler.h/cpp`: Логика TCP сервера.
    *   `tcp_session.h/cpp`: Логика обработки TCP сессии игрока.
    *   `command_consumer.h/cpp`: Компонент, читающий команды из RabbitMQ.
    *   `game_session.h/cpp`, `session_manager.h/cpp`, `tank.h/cpp`, `tank_pool.h/cpp`: Основная игровая логика.
    *   `kafka_producer_handler.h/cpp`: Обработчик для отправки сообщений в Kafka.
    *   `CMakeLists.txt`: Сборочный скрипт для этого компонента.
*   `monitoring/`: Конфигурационные файлы для системы мониторинга.
    *   `prometheus/prometheus.yml`: Конфигурация Prometheus.
    *   `grafana/`: (Потенциально) Конфигурации дашбордов Grafana.
*   `protos/`: Определения протоколов gRPC и сообщений Protobuf.
    *   `auth_service.proto`: Определение сервиса аутентификации.
*   `tests/`: Юнит-тесты для C++ компонентов.
    *   `CMakeLists.txt`: Сборочный скрипт для тестов.
    *   `main_test.cpp`: Основной файл для запуска тестов Catch2.
    *   `test_*.cpp`: Файлы с тестами для различных модулей.
*   `requirements.txt`: Список Python зависимостей.
*   `README.md`: Этот файл.

## Data Flows

### Регистрация пользователя:
1.  **Клиент -> Nginx -> C++ TCP Auth Server (`auth_server_cpp`):** Клиент отправляет TCP-запрос с данными для регистрации (например, логин, пароль в JSON-формате). Nginx проксирует этот запрос на C++ TCP Auth Server.
2.  **C++ TCP Auth Server -> Python Auth gRPC Service (`auth_server`):** C++ сервер парсит JSON, формирует gRPC-запрос `RegisterUser` и отправляет его в Python Auth gRPC Service.
3.  **Python Auth gRPC Service:**
    *   Проверяет, не занят ли запрошенный логин, обращаясь к Redis.
    *   Если логин свободен, хеширует пароль (например, с использованием bcrypt).
    *   Сохраняет нового пользователя (логин, хеш пароля, соль) в Redis.
    *   Публикует событие `user_registered` (содержащее, например, ID пользователя и логин) в топик `auth_events` в Kafka.
    *   Формирует gRPC-ответ (успех или ошибка с описанием) и отправляет его обратно в C++ TCP Auth Server.
4.  **C++ TCP Auth Server -> Клиент:** C++ сервер транслирует ответ от gRPC сервиса клиенту по TCP.

### Вход пользователя и начало игры:
1.  **Клиент -> Nginx -> C++ TCP Auth Server (`auth_server_cpp`):** Клиент отправляет TCP-запрос с учетными данными (логин, пароль в JSON) для входа.
2.  **C++ TCP Auth Server -> Python Auth gRPC Service (`auth_server`):** C++ сервер формирует gRPC-запрос `AuthenticateUser` и отправляет его в Python Auth gRPC Service.
3.  **Python Auth gRPC Service:**
    *   Извлекает данные пользователя из Redis по логину.
    *   Сравнивает предоставленный хеш пароля с сохраненным.
    *   В случае успеха, генерирует уникальный сессионный токен.
    *   Сохраняет сессионный токен в Redis, связывая его с ID пользователя и временем жизни.
    *   Публикует событие `user_loggedin` (с ID пользователя, токеном) в топик `auth_events` в Kafka.
    *   Возвращает gRPC-ответ с сессионным токеном (в случае успеха) или сообщением об ошибке.
4.  **C++ TCP Auth Server -> Клиент:** Передает клиенту сессионный токен или сообщение об ошибке.
5.  **Клиент -> Nginx -> C++ Game Server (`game_server_cpp`):** Клиент, получив токен, устанавливает новое TCP (или UDP для некоторых первичных сообщений) соединение с игровым сервером, передавая сессионный токен для "входа в игру".
6.  **C++ Game Server -> Python Auth gRPC Service (`auth_server`):** Игровой сервер (например, при установлении TCP-сессии игрока) получает токен от клиента и делает gRPC-запрос `ValidateSessionToken` к Python Auth gRPC Service для его проверки.
7.  **Python Auth gRPC Service:** Проверяет наличие и валидность токена в Redis. Возвращает gRPC-ответ с результатом валидации (например, ID пользователя, если токен валиден).
8.  **C++ Game Server:**
    *   Если токен валиден: создает или присоединяет игрока к игровой сессии (`GameSession`), выделяет свободный танк из пула (`TankPool`), связывает танк с игроком.
    *   Сообщает клиенту об успешном входе в игру, ID его танка и начальном состоянии игровой сессии (например, карта, другие игроки).
    *   Публикует событие `player_joined_session` в Kafka (`player_sessions_history`).

### Отправка команды игроком (например, движение):
1.  **Клиент -> Nginx -> C++ Game Server (`game_server_cpp`):** Клиент отправляет UDP (предпочтительно для частых обновлений) или TCP пакет, содержащий команду (например, "move"), идентификатор игрока (или сессионный токен, если требуется проверка на уровне обработчика) и параметры команды (например, новые координаты `{"x": 10, "y": 20}`).
2.  **C++ Game Server (UDP/TCP Handler):** Обработчик соответствующего протокола принимает сообщение, минимально валидирует его и формирует JSON-сообщение для внутренней обработки. Это сообщение публикуется в очередь `player_commands` в RabbitMQ. Сообщение может содержать `player_id`, тип команды, параметры и, возможно, временную метку.
3.  **C++ Player Command Handler (`PlayerCommandConsumer` в `game_server_cpp`):** Этот компонент является подписчиком очереди `player_commands` в RabbitMQ. Он читает сообщения с командами.
4.  **C++ Player Command Handler:** На основе `player_id` из сообщения, находит активную игровую сессию игрока (`GameSession`) и ассоциированный с ним объект танка (`Tank`).
5.  **C++ Player Command Handler:** Вызывает соответствующий метод у объекта танка для обновления его состояния (например, `tank->move(new_position)`). Логика внутри танка может включать проверки на допустимость движения, столкновения и т.д.
6.  **C++ Game Server (GameSession/Tank):** После изменения состояния танка, игровая сессия, к которой принадлежит игрок, обычно отвечает за уведомление других клиентов в этой же сессии об изменении состояния (например, рассылая обновленные координаты танка по UDP).
7.  **C++ Game Server (KafkaProducerHandler):** (Опционально, в зависимости от настроек логирования) Публикует событие о движении (например, `tank_moved` с ID танка, новыми координатами, временем) в соответствующий топик Kafka (например, `tank_coordinates_history`) для анализа или отладки.

## Requirements

### Общие требования
*   **Git:** Система контроля версий для клонирования репозитория.
*   **Docker & Docker Compose:** Для сборки и запуска контейнеризированных сервисов и самого приложения. Версия Docker Compose должна поддерживать формат `docker-compose.yml` версии 3.8+.

### Python Development
*   **Python:** Рекомендуется версия 3.9 или новее. Убедитесь, что Python добавлен в `PATH`.
*   **PIP:** Менеджер пакетов Python (обычно устанавливается вместе с Python).
*   **Виртуальное окружение (Рекомендуется):** Использование `venv` или `conda` для изоляции зависимостей проекта.
*   **Зависимости Python:** Полный список указан в файле `requirements.txt`. Ключевые библиотеки:
    *   `grpcio`, `grpcio-tools`: для gRPC.
    *   `redis`: для взаимодействия с Redis.
    *   `confluent-kafka`: для взаимодействия с Kafka.
    *   `pika`: для взаимодействия с RabbitMQ.
    *   `prometheus_client`: для метрик Prometheus.
    *   `pytest`, `pytest-asyncio`: для тестирования.
    *   `locust`: для нагрузочного тестирования.
    *   `passlib[bcrypt]`: для хеширования паролей.

### C++ Development
Для разработки C++ компонентов потребуется настроенное окружение.

*   **Компилятор C++:** Поддерживающий стандарт C++17 (например, GCC 8+, Clang 6+, MSVC Visual Studio 2019+).
*   **CMake:** Система автоматизации сборки.
    *   Локальная сборка: версия 3.16 или новее.
    *   Docker-сборка: используется версия CMake >= 3.29 (например, 3.29.6, как указано в `cpp/Dockerfile`) из-за использования политики `CMP0167`.
*   **`protoc` (Protocol Buffers Compiler) и `grpc_cpp_plugin` (gRPC C++ Plugin):**
    *   Необходимы для компиляции `.proto` файлов.
    *   **При использовании `vcpkg` для установки `grpc` (рекомендуется для Windows):** `protoc` и `grpc_cpp_plugin` обычно устанавливаются и интегрируются автоматически.
    *   **Для Linux:** Если gRPC устанавливается через системный менеджер пакетов (например, `apt`), убедитесь, что установлены пакеты `protobuf-compiler` и `libgrpc-dev` (или `grpc_cpp_plugin`).
    *   При ручной установке `protoc` должен быть в `PATH`.
*   **Менеджер пакетов `vcpkg` (Рекомендуется, особенно для Windows):**
    *   Инструкции по установке: [https://github.com/microsoft/vcpkg](https://github.com/microsoft/vcpkg)
        1.  Клонировать: `git clone https://github.com/microsoft/vcpkg.git && cd vcpkg`
        2.  Установить: `.\bootstrap-vcpkg.bat` (Windows) или `./bootstrap-vcpkg.sh` (Linux/macOS).
        3.  Интегрировать: `.\vcpkg integrate install`.
    *   **Установка зависимостей через `vcpkg` (пример для Windows x64):**
        ```powershell
        .\vcpkg install boost:x64-windows grpc:x64-windows librdkafka[cpp]:x64-windows librabbitmq:x64-windows nlohmann-json:x64-windows catch2:x64-windows openssl:x64-windows zlib:x64-windows c-ares:x64-windows re2:x64-windows
        ```
        *   Замените `:x64-windows` на ваш целевой триплет при необходимости.
*   **Альтернатива для Linux (системный менеджер пакетов, например, `apt` для Debian/Ubuntu):**
    ```bash
    sudo apt-get update
    sudo apt-get install -y build-essential cmake git pkg-config \
        libboost-dev libboost-system-dev \
        libgrpc++-dev libprotobuf-dev protobuf-compiler grpc-proto \
        librdkafka-dev librdkafka++-dev \
        librabbitmq-dev \
        nlohmann-json3-dev \
        catch2 \
        libssl-dev zlib1g-dev libc-ares-dev libre2-dev
    ```
    *   *Примечание: `grpc-proto` может потребоваться для плагина grpc cpp.*
    *   *Убедитесь в совместимости версий пакетов из системных репозиториев.*

## Installation

### 1. Клонирование репозитория
```bash
git clone <URL_вашего_репозитория> # Замените на URL вашего репозитория
cd <имя_каталога_проекта>
```

### 2. Настройка Python окружения
Рекомендуется использовать виртуальное окружение.
```bash
# Создание (например, python3 -m venv venv) и активация (source venv/bin/activate или .\venv\Scripts\activate)
pip install -r requirements.txt
```

### 3. Установка C++ зависимостей
Следуйте инструкциям в разделе [C++ Development](#c-development) для установки зависимостей с помощью `vcpkg` или системного менеджера пакетов.

### 4. Генерация gRPC кода

*   **Для C++:** Код генерируется автоматически во время CMake конфигурации/сборки проекта (цель `proto_lib` в `cpp/protos/CMakeLists.txt`). Убедитесь, что `protoc` и `grpc_cpp_plugin` доступны вашей системе сборки (обычно решается через `vcpkg` или установку соответствующих dev-пакетов).
*   **Для Python:** Сгенерированные файлы (`*_pb2.py`, `*_pb2_grpc.py`) должны находиться в `protos/generated/python/`. Если их нет или требуется обновление:
    1.  Убедитесь, что установлены `grpcio-tools`: `pip install grpcio-tools`
    2.  Из корневой директории проекта выполните команду (при необходимости создайте директорию `protos/generated/python`):
        ```bash
        python -m grpc_tools.protoc -I./protos --python_out=./protos/generated/python --pyi_out=./protos/generated/python --grpc_python_out=./protos/generated/python ./protos/auth_service.proto
        ```
        *Примечание: Docker-сборка для `auth_server` (`auth_server/Dockerfile`) ожидает, что эти файлы уже сгенерированы и будут скопированы из `protos/generated/python` в образ.*

### 5. Сборка C++ компонентов
Сборка осуществляется с помощью CMake.

1.  Перейдите в каталог `cpp`: `cd cpp`
2.  Создайте каталог для сборки и перейдите в него: `mkdir build && cd build`
    *Все последующие команды CMake и сборки выполняются из каталога `cpp/build/`.*

**Для Windows (Visual Studio с `vcpkg`):**
*   Убедитесь, что `vcpkg integrate install` был выполнен.
*   Конфигурация (замените путь к `vcpkg.cmake` и генератор Visual Studio при необходимости):
    ```powershell
    cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_TOOLCHAIN_FILE="C:/path/to/your/vcpkg/scripts/buildsystems/vcpkg.cmake"
    ```
*   Сборка (Release):
    ```powershell
    cmake --build . --config Release
    ```
    Или Debug: `cmake --build . --config Debug`
    Или откройте `.sln` файл в Visual Studio и соберите оттуда.

**Для Linux/macOS (GCC/Clang):**
*   Конфигурация (если используете `vcpkg`, добавьте `-DCMAKE_TOOLCHAIN_FILE`):
    ```bash
    cmake .. -DCMAKE_BUILD_TYPE=Release 
    ```
*   Сборка:
    ```bash
    make -j$(nproc)
    # или cmake --build . --config Release
    ```
Исполняемые файлы будут в подкаталогах `cpp/build/auth_server_cpp/` и `cpp/build/game_server_cpp/` (и `cpp/build/tests/` для тестов).

## Running the Application

### Через Docker Compose (Рекомендуемый способ)
Это основной способ для запуска всего стека приложения, включая все C++ и Python сервисы, а также инфраструктурные компоненты (Kafka, RabbitMQ, Redis, Zookeeper, Prometheus, Grafana).
1.  Убедитесь, что Docker Desktop (для Windows/Mac) или Docker Engine/CLI (для Linux) установлен и запущен.
2.  Из корневой директории проекта выполните:
    ```bash
    docker compose up --build -d
    ```
    *   `--build`: Пересобирает образы, если были изменения в Dockerfile или исходном коде.
    *   `-d`: Запускает контейнеры в фоновом (detached) режиме.
3.  Для остановки сервисов:
    ```bash
    docker compose down
    ```
4.  Для просмотра логов:
    ```bash
    docker compose logs -f [имя_сервиса] # например, docker compose logs -f cpp_game_server
    # или для всех сервисов: docker compose logs -f
    ```

### Локальный запуск отдельных компонентов
Этот способ может быть полезен для разработки и отладки отдельных сервисов. Требует, чтобы все зависимые инфраструктурные компоненты (Kafka, RabbitMQ, Redis) были запущены и доступны (например, через Docker Compose без запуска самих разрабатываемых сервисов, или установлены локально).

*   **Python Auth gRPC Service (`auth_server`):**
    1.  Убедитесь, что Redis и Kafka (если используется) доступны.
    2.  Активируйте Python виртуальное окружение: `source venv/bin/activate` (Linux/macOS) или `.\venv\Scripts\activate` (Windows).
    3.  Установите переменные окружения (если не заданы глобально):
        ```bash
        export REDIS_HOST=localhost 
        export REDIS_PORT=6379
        export KAFKA_BOOTSTRAP_SERVERS=localhost:29092 
        # (Порт Kafka 29092 если он мапится на localhost из Docker, или 9092 если Kafka локально)
        ```
    4.  Запустите из корневой директории проекта:
        ```bash
        python -m auth_server.auth_grpc_server
        ```
        Сервис будет слушать на порту `50051`.

*   **C++ TCP Auth Server (`auth_server_cpp`):**
    1.  Убедитесь, что Python Auth gRPC Service запущен и доступен.
    2.  Соберите проект (см. раздел "Сборка C++ компонентов").
    3.  Запустите исполняемый файл (путь может отличаться в зависимости от конфигурации сборки, например, Debug/Release):
        ```bash
        # Пример для Release сборки на Linux из cpp/build/
        ./auth_server_cpp/auth_server_app --port 9000 --grpc_addr localhost:50051 
        ```

*   **C++ Game Server (`game_server_cpp`):**
    1.  Убедитесь, что Python Auth gRPC Service, RabbitMQ и Kafka запущены и доступны.
    2.  Соберите проект.
    3.  Запустите исполняемый файл, указав необходимые параметры:
        ```bash
        # Пример для Release сборки на Linux из cpp/build/
        ./game_server_cpp/game_server_app --tcp_port 8888 --udp_port 8889 \
        --rmq_host localhost --rmq_port 5672 --rmq_user user --rmq_pass password \
        --kafka_brokers localhost:29092 \
        --auth_grpc_host localhost --auth_grpc_port 50051
        ```
        *Примечание: Адаптируйте хосты и порты в зависимости от того, как у вас запущена инфраструктура.*

## Стратегия тестирования и окружения

В проекте применяется многоуровневая стратегия тестирования для обеспечения качества и надежности различных компонентов системы. Тестирование проводится в различных окружениях, чтобы максимально покрыть возможные сценарии использования.

### Типы тестов:

1.  **C++ Юнит-тесты:**
    *   **Цель:** Проверка корректности отдельных модулей и классов C++ кода (игровая логика, обработчики сетевых протоколов, утилиты).
    *   **Инструменты:** Catch2.
    *   **Окружение:** Запускаются локально после сборки C++ компонентов или могут быть интегрированы в Docker-сборку. Не требуют внешних зависимостей, как базы данных или брокеры сообщений (используют mock-объекты, где это необходимо).

2.  **Python Юнит-тесты:**
    *   **Цель:** Проверка отдельных модулей и функций Python-сервисов (логика аутентификации, взаимодействие с Redis/Kafka на уровне клиентов с использованием mock-объектов).
    *   **Инструменты:** `pytest`, `pytest-asyncio`.
    *   **Окружение:** Запускаются локально. Внешние сервисы (Redis, Kafka) мокаются.

3.  **Python Интеграционные тесты:**
    *   **Цель:** Проверка взаимодействия между несколькими сервисами системы (например, полный цикл аутентификации через C++ TCP Auth Server и Python Auth gRPC Service, или взаимодействие Game Server с Auth Service).
    *   **Инструменты:** `pytest`, `pytest-asyncio`, реальные клиенты к сервисам.
    *   **Окружение:** Требуют полностью развернутого стека приложения, включая все C++ и Python сервисы, а также инфраструктурные компоненты (Kafka, RabbitMQ, Redis). Обычно запускаются при помощи `docker compose`.

4.  **Нагрузочные тесты:**
    *   **Цель:** Оценка производительности и стабильности ключевых сервисов под высокой нагрузкой.
    *   **Инструменты:** Locust.
    *   **Окружение:** Требуют развернутых целевых сервисов (например, Auth Service или Game Service) и их зависимостей.

### Окружения для тестирования:

*   **Локальное окружение разработчика (Windows/Linux/macOS):**
    *   Используется для разработки и частого запуска юнит-тестов.
    *   C++ компоненты могут собираться с помощью системного компилятора и CMake, либо с использованием `vcpkg` (особенно рекомендуется для Windows для управления C++ зависимостями).
    *   Python тесты запускаются в виртуальном окружении.
    *   Для интеграционных и нагрузочных тестов инфраструктурные зависимости (Kafka, RabbitMQ, Redis) могут быть запущены локально через Docker Compose.

*   **Docker-окружение (через `docker-compose.yml`):**
    *   Основное окружение для интеграционных тестов и для эмуляции production-подобной среды.
    *   `cpp/Dockerfile` используется для сборки C++ сервисов в контролируемом Linux-окружении (Ubuntu 22.04).
    *   `auth_server/Dockerfile` используется для Python сервиса.
    *   C++ юнит-тесты могут быть выполнены внутри builder-стадии Docker-образа C++ сервисов (путем добавления команды `make test` или `ctest` в Dockerfile) или путем запуска тестового исполняемого файла в контейнере.

Раздел "## Testing" ниже содержит детальные инструкции по запуску каждого типа тестов.

## Testing

### C++ Юнит-тесты

Юнит-тесты для C++ компонентов написаны с использованием фреймворка [Catch2](https://github.com/catchorg/Catch2) (v3.x).

**Расположение файлов:**
*   Исходный код тестов находится в директории `cpp/tests/`.
*   Основной файл для запуска тестов (main): `cpp/tests/main_test.cpp`.
*   Индивидуальные тестовые случаи размещены в файлах `cpp/tests/test_*.cpp`.

**Сборка тестов:**
*   Тесты автоматически конфигурируются и собираются вместе с основными C++ компонентами при сборке проекта с помощью CMake.
*   Убедитесь, что в корневом `cpp/CMakeLists.txt` включено тестирование (`enable_testing()`) и добавлена директория тестов (`add_subdirectory(tests)`). Это уже настроено в проекте.
*   Исполняемый файл с тестами обычно называется `game_tests` (или `game_tests.exe` для Windows) и помещается в каталог сборки, например, `cpp/build/tests/Release/` или `cpp/build/tests/Debug/` в зависимости от конфигурации сборки.

**Запуск тестов:**
Все команды следует выполнять из вашего каталога сборки C++ (например, `cpp/build/`).

1.  **Через CTest (рекомендуемый способ, если настроено):**
    CTest — это инструмент для запуска тестов, интегрированный с CMake. Он позволяет запускать все зарегистрированные тесты и предоставляет сводный отчет.
    ```bash
    # Для конфигурации Release (наиболее частый случай для CI или финального тестирования)
    ctest -C Release
    
    # Для конфигурации Debug
    ctest -C Debug
    
    # Для более подробного вывода
    ctest -C Release -V
    # или для вывода только при ошибках
    ctest -C Release --output-on-failure
    ```
    *Примечание: `add_test(NAME GameLogicUnitTests COMMAND game_tests)` в `cpp/tests/CMakeLists.txt` регистрирует исполняемый файл `game_tests` для запуска через CTest.*

2.  **Напрямую запуская исполняемый файл:**
    Это дает больше контроля над параметрами запуска Catch2.

    *   **Linux/macOS:**
        ```bash
        # Для конфигурации Release
        ./tests/Release/game_tests [аргументы Catch2]
        # Пример: запустить тесты с тегом "network"
        ./tests/Release/game_tests [network]
        # Пример: запустить конкретный тест по имени
        ./tests/Release/game_tests "Название конкретного теста"
        ```
    *   **Windows (например, в Git Bash или PowerShell):**
        ```powershell
        # Для конфигурации Release
        ./tests/Release/game_tests.exe [аргументы Catch2]
        # Пример: запустить тесты с тегом "network"
        ./tests/Release/game_tests.exe [network]
        # Пример: вывести список всех тестов
        ./tests/Release/game_tests.exe --list-tests
        ```
    *   **Популярные аргументы Catch2:**
        *   `--list-tests` (`-l`): Показать список всех доступных тестов.
        *   `--list-tags` (`-t`): Показать список всех тегов.
        *   `[тег]` или `"[тег1][тег2]"`: Запустить тесты с указанными тегами.
        *   `"название теста"`: Запустить конкретный тест (можно использовать wildcard `*`).
        *   `-r <reporter>`: Использовать определенный формат вывода (например, `xml`, `junit`, `console`).
        *   `-s`: Показать успешные тесты.
        *   `-b` или `--break`: Войти в отладчик при падении теста (если отладчик настроен).
        *   Полный список аргументов: `./tests/Release/game_tests --help`

**Добавление новых тестов:**
1.  Создайте новый файл `test_my_feature.cpp` в директории `cpp/tests/`.
2.  Включите необходимые заголовки и `#include "catch2/catch_all.hpp"`.
3.  Пишите тестовые случаи, используя макросы Catch2, такие как `TEST_CASE`, `SECTION`, `REQUIRE`, `CHECK`.
    ```cpp
    #include "catch2/catch_all.hpp"
    // #include "path/to/your/header.h" // Заголовок тестируемого модуля

    TEST_CASE("My feature test", "[my_feature_tag]") {
        // ... ваш код теста ...
        int value = 42;
        REQUIRE(value == 42);
    }
    ```
4.  Добавьте новый файл `test_my_feature.cpp` в список исходников для цели `game_tests` в `cpp/tests/CMakeLists.txt`:
    ```cmake
    add_executable(game_tests
        main_test.cpp
        # ... другие тестовые файлы ...
        test_my_feature.cpp 
    )
    ```
5.  Пересоберите проект. Ваш новый тест должен быть скомпилирован и доступен для запуска.

**Запуск тестов в Docker:**
В настоящее время запуск C++ юнит-тестов не интегрирован как отдельный шаг в `cpp/Dockerfile` или `docker-compose.yml`. Для запуска тестов в окружении, максимально приближенном к Docker:
1.  Соберите C++ builder образ: `docker compose build cpp_game_server` (или `cpp_auth_server`, так как они используют один и тот же `cpp/Dockerfile`).
2.  Запустите контейнер из этого образа в интерактивном режиме, смонтировав исходный код (если он не был скопирован на нужном этапе):
    ```bash
    # Предполагается, что сборка уже была выполнена внутри образа на предыдущем шаге
    # или вы запускаете сборку и тесты внутри контейнера
    docker run -it --rm -v $(pwd)/cpp:/app/src <имя_образа_builder_из_docker_compose> bash
    # Внутри контейнера:
    cd /app/src/build_release/
    ctest -C Release -V 
    # или
    ./tests/Release/game_tests
    ```
    Либо можно добавить шаг `RUN make test` или `RUN ctest -C Release` в `cpp/Dockerfile` после шага сборки C++ приложений, если требуется автоматический запуск тестов при каждой сборке образа.

### Python Юнит-тесты

Юнит-тесты для Python компонентов написаны с использованием фреймворка [pytest](https://docs.pytest.org/). Для тестирования асинхронного кода используется [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio).

**Расположение файлов:**
*   Исходный код юнит-тестов находится в директории `tests/unit/` (относительно корневой директории проекта `tests/python/`, но обычно `pytest` запускается из корня проекта, и он находит их по стандартным соглашениям).
*   Примеры файлов: `tests/unit/test_auth_service.py`, `tests/unit/test_command_consumers.py` и т.д.

**Подготовка к запуску:**
1.  Убедитесь, что вы находитесь в корневой директории проекта.
2.  Активируйте ваше Python виртуальное окружение (например, `source venv/bin/activate` или `.venv\Scripts\activate`).
3.  Установите зависимости для разработки, включая `pytest` и `pytest-asyncio`, если это еще не сделано:
    ```bash
    pip install -r requirements.txt 
    # Убедитесь, что pytest и pytest-asyncio есть в requirements.txt или установлены отдельно
    # pip install pytest pytest-asyncio
    ```

**Запуск тестов:**
Команды выполняются из корневой директории проекта.

1.  **Запуск всех юнит-тестов:**
    ```bash
    pytest tests/unit/
    # или просто
    pytest 
    # (если pytest настроен на автоматическое обнаружение тестов в директории tests/)
    # или
    python -m pytest tests/unit/
    ```

2.  **Запуск тестов в конкретном файле:**
    ```bash
    pytest tests/unit/test_auth_service.py
    ```

3.  **Запуск конкретного теста по имени (функции или класса):**
    Используйте опцию `-k` для указания выражения, совпадающего с именем теста.
    ```bash
    # Запустит все тесты, содержащие "test_authenticate_user" в названии
    pytest tests/unit/test_auth_service.py -k "test_authenticate_user"
    
    # Запустит тест TestUserService.test_create_user (если есть такой класс и метод)
    pytest tests/unit/test_auth_service.py -k "TestUserService and test_create_user" 
    ```

4.  **Запуск тестов по маркеру (если используются):**
    Если тесты помечены маркерами (например, `@pytest.mark.slow`), их можно запускать так:
    ```bash
    pytest -m slow # Запустить тесты с маркером 'slow'
    pytest -m "not slow" # Запустить все тесты, кроме помеченных 'slow'
    ```
    *Примечание: В текущей структуре проекта явное использование маркеров не очевидно, но это стандартная возможность pytest.*

5.  **Вывод информации:**
    *   `-v`: Более подробный вывод.
    *   `-s`: Показывать вывод `print()` из тестов.
    *   `--cov=.` или `--cov=auth_server --cov=core`: Для генерации отчета о покрытии кода (требует `pytest-cov`).

**Добавление новых тестов:**
1.  Создайте новый Python-файл с префиксом `test_` (например, `test_my_new_module.py`) в директории `tests/unit/`.
2.  Импортируйте необходимые модули и `pytest`.
3.  Пишите тестовые функции с префиксом `test_` или создавайте классы с префиксом `Test` (которые содержат методы с префиксом `test_`).
    ```python
    # tests/unit/test_my_new_module.py
    # import pytest # Обычно не требуется для простых тестов, но может быть нужен для фикстур и маркеров
    # from your_project_module import my_function # Импорт тестируемого кода

    def test_my_functionality():
        # result = my_function(params)
        # assert result == expected_value
        assert True # Пример

    # Для асинхронных функций:
    # @pytest.mark.asyncio
    # async def test_my_async_function():
    #     await asyncio.sleep(0) # Пример асинхронного вызова
    #     assert True
    ```
4.  `pytest` автоматически обнаружит и запустит новые тесты при следующем вызове.

**Зависимости для тестов:**
*   Для Python юнит-тестов обычно не требуются внешние сервисы (как Redis, Kafka), так как они должны использовать mock-объекты или заглушки для изоляции тестируемого кода.

### Нагрузочное тестирование (Locust)

Для нагрузочного тестирования используется [Locust](https://locust.io/). Locust позволяет описывать поведение пользователей в Python коде и симулировать тысячи одновременных пользователей.

**Расположение файлов:**
*   Скрипты Locust (locustfiles) находятся в директории `tests/load/`.
    *   `locustfile_auth.py`: Для нагрузочного тестирования сервиса аутентификации.
    *   `locustfile_game.py`: Заготовка или пример для нагрузочного тестирования игрового сервера (требует доработки).

**Подготовка к запуску:**
1.  **Запуск окружения:** Убедитесь, что все необходимые сервисы (особенно те, которые вы собираетесь тестировать, и их зависимости) запущены. Обычно это делается через `docker compose up --build -d`.
2.  **Python окружение:**
    *   Активируйте ваше Python виртуальное окружение.
    *   Установите Locust, если это еще не сделано (он должен быть в `requirements.txt`):
        ```bash
        pip install locust
        ```

**1. Тестирование Сервиса Аутентификации (`locustfile_auth.py`)**

Этот locustfile (`tests/load/locustfile_auth.py`) тестирует C++ TCP Auth Server (`cpp_auth_tcp_server`), который по умолчанию работает на порту `9000` (согласно `docker-compose.yml`).
Скрипт использует кастомный `TCPClient` для отправки JSON-запросов на регистрацию и аутентификацию.

*   **Запуск Locust с веб-интерфейсом:**
    ```bash
    locust -f tests/load/locustfile_auth.py
    ```
    После запуска откройте в браузере `http://localhost:8089` (стандартный порт Locust Web UI).
    *   В поле "Host" указывать URL не обязательно, так как хост и порт (`localhost:9000`) заданы в самом locustfile (`AuthUser.host` и `AuthUser.port`). Однако, если вы хотите переопределить хост и порт через UI или командную строку Locust, это возможно. *Примечание: значение по умолчанию `AuthUser.port` в файле может быть `8888`, его следует либо исправить на `9000` для соответствия `docker-compose.yml`, либо всегда переопределять при запуске.*
    *   Укажите количество пользователей ("Number of users") и скорость их появления ("Spawn rate").
    *   Нажмите "Start swarming".

*   **Запуск Locust без веб-интерфейса (headless):**
    ```bash
    # Пример: 10 пользователей, 2 пользователя в секунду, продолжительность 60 секунд
    # Убедитесь, что AuthUser.host и AuthUser.port в locustfile_auth.py 
    # соответствуют вашему cpp_auth_tcp_server (например, localhost:9000)
    # или переопределите их через переменные окружения или аргументы, если Locust это поддерживает для кастомных User-ов.
    # Поскольку хост и порт жестко заданы в TCPClient, команда --host здесь не повлияет на TCPClient.
    locust -f tests/load/locustfile_auth.py AuthUser --headless -u 10 -r 2 --run-time 60s
    ```

*   **Важно по `locustfile_auth.py`:**
    *   Убедитесь, что `AuthUser.host` и `AuthUser.port` в `locustfile_auth.py` соответствуют адресу и порту вашего `cpp_auth_tcp_server` (в Docker это `localhost:9000`). По умолчанию в файле может быть указан порт `8888`, что неверно для сервиса аутентификации.
    *   Формат запросов в `locustfile_auth.py` должен соответствовать тому, что ожидает `auth_server_cpp` (JSON с полем `action`).

**2. Тестирование Игрового Сервиса (`locustfile_game.py`)**

Файл `tests/load/locustfile_game.py` является заготовкой и требует реализации для тестирования C++ Game Server (`cpp_game_server`), который работает с TCP (порт `8888`) и UDP (порт `8889`).

*   **Задачи при разработке `locustfile_game.py`:**
    *   Реализовать кастомные клиенты Locust для TCP и UDP, способные отправлять JSON-сообщения в формате, ожидаемом игровым сервером.
    *   Определить сценарии поведения пользователей:
        *   Подключение к серверу, отправка токена аутентификации (полученного от `auth_server`).
        *   Отправка команд движения (UDP).
        *   Отправка команд стрельбы (UDP).
        *   Отправка сообщений чата (TCP).
        *   Обработка ответов от сервера (если таковые предусмотрены для данных действий).
    *   Учитывать состояние игры и сессии для каждого виртуального пользователя.

*   **Примерный запуск (после реализации):**
    ```bash
    # Команда будет зависеть от реализации User-класса в locustfile_game.py
    locust -f tests/load/locustfile_game.py GameUser --headless -u 50 -r 5 --run-time 2m 
    ```

**Интерпретация результатов в Locust UI:**
*   **Statistics:** Основные метрики (количество запросов, ошибки, RPS, среднее время отклика, медиана, 90-й перцентиль и т.д.).
*   **Failures:** Список ошибок, возникших во время теста, с их частотой.
*   **Charts:** Графики изменения RPS, времени отклика и количества пользователей во времени.
*   **Download Data:** Возможность скачать отчеты в CSV формате.

Обращайте внимание на количество ошибок (Failures) и рост времени отклика при увеличении нагрузки. Это поможет выявить узкие места в производительности ваших сервисов.

### Python Интеграционные тесты

Интеграционные тесты предназначены для проверки взаимодействия между различными компонентами системы в окружении, приближенном к рабочему. Они используют `pytest` и `pytest-asyncio`.

**Расположение файлов:**
*   Основной файл с интеграционными тестами: `tests/test_integration.py` (относительно корневой директории проекта `tests/python/`, но обычно `pytest` запускается из корня проекта).
    *   *Примечание: Ранее в структуре упоминалась директория `tests/python/integration/`, но текущие логи `ls` показали `tests/test_integration.py` на верхнем уровне `tests/`. Если структура изменилась, этот путь должен быть актуальным. Если файл находится в `tests/python/integration/test_integration.py`, команда запуска должна это отражать.*

**Что тестируется (примеры):**
*   Взаимодействие между C++ TCP Auth Server и Python Auth gRPC Service (полный цикл аутентификации/регистрации).
*   Взаимодействие C++ Game Server с Python Auth gRPC Service для валидации токенов.
*   Корректность отправки и получения сообщений через брокеры сообщений (Kafka, RabbitMQ) между сервисами.
*   Базовые сценарии взаимодействия с Redis.

**Подготовка к запуску:**
1.  **Запуск полного окружения:** Для интеграционных тестов **необходимо**, чтобы все сервисы (C++ и Python серверы, Kafka, RabbitMQ, Redis, Zookeeper) были запущены и работали корректно. Самый простой способ это сделать — через Docker Compose:
    ```bash
    # Из корневой директории проекта
    docker compose up --build -d
    ```
    Дождитесь, пока все контейнеры запустятся и healthchecks (если настроены) пройдут успешно.

2.  **Python окружение:**
    *   Убедитесь, что вы находитесь в корневой директории проекта.
    *   Активируйте ваше Python виртуальное окружение.
    *   Установите зависимости для разработки: `pip install -r requirements.txt`.

**Запуск тестов:**
Команды выполняются из корневой директории проекта.

1.  **Запуск всех интеграционных тестов:**
    ```bash
    # Если файл tests/test_integration.py находится в tests/python/integration/
    pytest tests/python/integration/test_integration.py
    # Если файл tests/test_integration.py находится напрямую в tests/
    # pytest tests/test_integration.py 
    # (Уточните путь в зависимости от актуальной структуры)

    # Для более подробного вывода:
    pytest -v tests/python/integration/test_integration.py 
    ```
    *Примечание: Если есть другие файлы интеграционных тестов, их можно запускать аналогично или указать всю директорию `tests/python/integration/`.*

2.  **Конфигурация тестов:**
    *   Интеграционные тесты могут использовать переменные окружения для подключения к сервисам (например, адреса и порты Kafka, RabbitMQ, gRPC-сервисов). Убедитесь, что эти переменные настроены так, чтобы указывать на сервисы, запущенные через Docker Compose (например, `localhost` с соответствующими портами, или имена сервисов Docker, если тесты запускаются из контейнера, что в данном случае не предполагается для Python-тестов).
    *   Обычно для локального запуска с `docker-compose`, сервисы доступны по `localhost:<порт_маппинга>`.

**Добавление новых интеграционных тестов:**
1.  Определите сценарий взаимодействия между несколькими компонентами, который вы хотите протестировать.
2.  Добавляйте новые тестовые функции в `tests/test_integration.py` (или создавайте новые файлы в `tests/python/integration/` с префиксом `test_`).
3.  Используйте `pytest` и `pytest-asyncio` для написания тестов.
4.  В тестах подключайтесь к сервисам, используя их адреса и порты, как они сконфигурированы в `docker-compose.yml` и доступны с хост-машины (обычно `localhost:[порт]`).
5.  Используйте подходящие клиенты для взаимодействия с сервисами (например, `grpc.aio` для gRPC, `pika` для RabbitMQ, `confluent_kafka` для Kafka, `redis` для Redis).
6.  Не забывайте про корректную очистку состояния после тестов, если они создают данные в Redis, Kafka или RabbitMQ, чтобы тесты были идемпотентными. Это можно делать с помощью `pytest` фикстур.

## Contributing
(Содержимое этого раздела оставлено без изменений)
...

## Стабилизация Окружения и Улучшения Сборки

В ходе недавних доработок были решены следующие ключевые проблемы, направленные на повышение стабильности Docker-окружения и исправление процесса сборки C++ компонентов:

### 1. Стабилизация Запуска Docker-контейнеров

*   **Проблема:** Наблюдались ошибки подключения C++ сервисов (`cpp_game_server`, `cpp_auth_server`) к брокерам сообщений (Kafka, RabbitMQ) из-за того, что C++ сервисы стартовали и пытались установить соединения до полной готовности зависимых сервисов.
*   **Решение:**
    *   В файл `docker-compose.yml` были добавлены и настроены секции `healthcheck` для ключевых инфраструктурных сервисов:
        *   **Kafka:** Изначально использовалась команда `kafka-topics.sh --list`, затем `kafka-broker-api-versions.sh`, но в итоге для большей надежности и быстроты проверки была выбрана команда `nc -z localhost 9092 || exit 1`. Таймауты (`start_period`, `timeout`) были подобраны для обеспечения корректной проверки.
        *   **RabbitMQ:** Используется стандартная проверка `rabbitmq-diagnostics -q check_running`.
        *   **Redis:** Добавлена проверка с помощью `redis-cli ping`.
    *   Секции `depends_on` для сервисов, зависящих от Kafka, RabbitMQ и Redis, были обновлены с использованием условия `condition: service_healthy`. Это гарантирует, что зависимые сервисы (например, `auth_server`, `cpp_game_server`) запускаются только после того, как их критические зависимости сообщат о своей полной работоспособности. Для сервисов, не имеющих явного healthcheck (например, `auth_server` при зависимости от него других C++ сервисов), используется `condition: service_started`.

### 2. Улучшение Подключений в C++ Сервисах

*   **Проблема:** Даже при корректном порядке запуска сервисов, наблюдались периодические сбои при установке соединений из C++ кода к Kafka и RabbitMQ.
*   **Решение:**
    *   **`KafkaProducerHandler`**: В конструктор добавлен механизм повторных попыток (до 5 раз с задержкой) для создания соединения с Kafka. Улучшено логирование процесса подключения.
    *   **`PlayerCommandConsumer` (RabbitMQ)**: Значительно переработана логика `connect_to_rabbitmq()`. Добавлено детальное логирование ошибок AMQP на каждом шаге (login, channel open, queue declare, consume), включая анализ RPC-ответов. Улучшена обработка ошибок для предотвращения разрыва соединения. Механизм retry в цикле потребления (`consume_loop`) был сохранен и теперь работает с более надежной процедурой установки соединения.
    *   **`GameUDPHandler` (RabbitMQ)**: Аналогично `PlayerCommandConsumer`, в метод `setup_rabbitmq_connection()` добавлена логика повторных попыток (до 5 раз с задержкой) и улучшенное логирование ошибок AMQP.

### 3. Исправление Сборки C++ Компонентов в Docker

*   **Проблема:** После обновления CMake-скриптов для локальной сборки (добавление `cmake_policy(SET CMP0167 NEW)`), Docker-сборка C++ компонентов завершалась ошибкой `Policy "CMP0167" is not known to this version of CMake.`, так как версия CMake в Docker-образе (3.28.3) была ниже требуемой (>=3.29).
*   **Решение:**
    *   Файл `cpp/Dockerfile` был обновлен для установки более новой версии CMake (**3.29.6**). Это включает изменение URL для скачивания исходников CMake, его сборку и установку в Docker-образе.
    *   В командах вызова `cmake` внутри Dockerfile теперь используется полный путь `/usr/local/bin/cmake`, чтобы гарантированно использовать установленную версию, а не потенциально существующую системную. (Примечание: проверка хеш-суммы не была добавлена в рамках этого изменения, но является хорошей практикой на будущее).

### 4. Исправление Локальной Сборки C++ под Windows (с vcpkg)

*   **Проблема:** Возникали ошибки линковки `RabbitMQC::rabbitmq-c` для тестового проекта `game_tests` и многочисленные предупреждения компилятора о deprecated include-путях для `rabbitmq-c`, а также предупреждения CMake о политике `CMP0167` для `FindBoost`.
*   **Решение:**
    *   **Линковка `rabbitmq-c` в тестах**: В `cpp/tests/CMakeLists.txt` была скорректирована логика поиска и использования цели для `rabbitmq-c`. Теперь используется переменная `RabbitMQ_LINK_TARGET`, которая устанавливается в зависимости от того, используется ли `vcpkg` (цель `rabbitmq::rabbitmq`) или `pkg-config` (цель `RabbitMQC::rabbitmq-c`).
    *   **Deprecated includes `rabbitmq-c`**: Во всех релевантных C++ заголовочных файлах (`.h`) старые пути вида `#include <amqp.h>` были заменены на новые, с префиксом `rabbitmq-c/` (например, `#include <rabbitmq-c/amqp.h>`).
    *   **Политика `CMP0167` (FindBoost)**: В корневой `cpp/CMakeLists.txt` и CMake-файлы основных компонентов (`game_server_cpp`, `auth_server_cpp`, `tests`) была добавлена строка `cmake_policy(SET CMP0167 NEW)` для использования современного механизма поиска Boost и устранения предупреждений.

Эти изменения обеспечивают более стабильную и предсказуемую работу как Docker-окружения, так и процесса локальной сборки C++ компонентов.

## Future Improvements
(Содержимое этого раздела оставлено без изменений)
...
