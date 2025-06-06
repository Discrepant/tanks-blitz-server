# Сервер игры "Танковые Сражения"

Этот проект представляет собой бэкенд-сервер для многопользовательской игры в танковые сражения. Он обладает микросервисной архитектурой с компонентами для аутентификации и игровой логики, поддерживая реализации на Python и C++ для различных частей системы.

## Содержание

- [Цели проекта](#цели-проекта)
- [Обзор архитектуры](#обзор-архитектуры)
- [Детальное Описание Сервисов](#детальное-описание-сервисов)
- [Структура каталогов](#структура-каталогов)
- [Потоки данных](#потоки-данных)
- [Требования](#требования)
- [Установка](#установка)
- [Запуск приложения](#запуск-приложения)
- [Тестирование](#тестирование)
- [Вклад в проект](#вклад-в-проект)
- [Стабилизация Окружения и Улучшения Сборки](#стабилизация-окружения-и-улучшения-сборки)
- [Будущие улучшения](#будущие-улучшения)

## Цели проекта

*   **Создание масштабируемого и высокопроизводительного бэкенда:** Разработать серверную часть для многопользовательской игры в танковые сражения в реальном времени, способную выдерживать значительные нагрузки и обеспечивать минимальные задержки.
*   **Разделение на микросервисы:** Реализовать независимые сервисы для аутентификации пользователей и игровой логики, что упрощает разработку, тестирование, развертывание и масштабирование отдельных компонентов системы.
*   **Эффективное межсервисное взаимодействие с помощью gRPC:** Использовать gRPC для быстрой и надежной коммуникации между внутренними сервисами, например, между C++ TCP сервером аутентификации и Python gRPC сервисом аутентификации.
*   **Асинхронная обработка задач и потоковая передача событий:** Применять очереди сообщений, такие как Kafka (для потоковой передачи событий, например, истории сессий, игровых событий) и RabbitMQ (для асинхронной обработки команд игроков), для повышения отказоустойчивости и снижения связанности компонентов.
*   **Надежное хранение данных с Redis:** Использовать Redis в качестве быстрого и эффективного хранилища данных для пользовательских сессий, кеширования и другой оперативной информации, доступ к которому осуществляется из Python сервиса аутентификации.
*   **Поддержка контейнеризации и оркестрации:** Обеспечить возможность развертывания приложения с использованием Docker-контейнеров и управления ими с помощью Kubernetes для упрощения развертывания, масштабирования и управления в различных средах.
*   **Интеграция системы мониторинга:** Внедрить Prometheus для сбора и отображения метрик производительности и состояния различных компонентов системы, что помогает в своевременном обнаружении и диагностике проблем.
*   **Гибкость разработки и производительность с Python и C++:** Предложить реализации серверных компонентов как на Python (для скорости разработки и удобства), так и на C++ (для критически важных по производительности частей, таких как игровой сервер), чтобы сбалансировать скорость разработки и эффективность выполнения.
*   **Повышение отказоустойчивости и наблюдаемости:** Внедрение механизмов для обеспечения стабильной работы сервисов при сбоях (например, healthchecks, retry-механизмы) и сбор детальной информации (логи, метрики) для анализа и отладки.

## Обзор архитектуры

Система спроектирована как набор взаимодействующих микросервисов, обеспечивающих различные аспекты игры и аутентификации.

### Компоненты Системы (Краткий Обзор)

1.  **Nginx (Концептуально):**
    *   **Роль:** Выполняет функции основной входной точки для всего клиентского трафика, обеспечивает SSL-терминацию, балансировку нагрузки и проксирование запросов к соответствующим бэкенд-сервисам.
    *   **Взаимодействие:** Принимает весь внешний трафик от пользователей.

2.  **Сервис Аутентификации:** Состоит из нескольких реализаций:
    *   **C++ TCP Auth Server (`auth_server_cpp`):** Внешний TCP-интерфейс для клиентов; проксирует запросы аутентификации/регистрации на Python Auth gRPC Service.
    *   **Python Auth Service (TCP/JSON)**: Запускается `auth_server/main.py`. Используется Python `game_server`.
    *   **Python Auth Service (gRPC)**: Запускается `auth_server/auth_grpc_server.py`. Используется C++ `auth_server_cpp` и, предположительно, C++ `game_server_cpp`.

3.  **C++ Game Server (компонент `game_server_cpp`):**
    *   **Роль:** Обрабатывает всю логику игрового процесса в реальном времени (движение, стрельба, игровые сессии).
    *   **Взаимодействие:** Общается с клиентами по TCP/UDP, использует RabbitMQ для очередей команд, Kafka для игровых событий и Python Auth gRPC Service для валидации сессий.

4.  **Python Game Server (`game_server/`)**:
    *   **Роль:** Альтернативная/полноценная реализация игрового сервера на Python. Обрабатывает игровую логику, TCP/UDP соединения от клиентов.
    *   **Взаимодействие:** Общается с клиентами по TCP/UDP, использует Python Auth TCP/JSON Service для аутентификации, RabbitMQ для команд, Kafka для событий.

5.  **Брокеры Сообщений:**
    *   **Kafka:** Для потоковой передачи событий (события аутентификации из Python Auth gRPC Service - концептуально; игровые события и история сессий из C++ Game Server, события из Python Game Server - концептуально).
    *   **RabbitMQ:** Для асинхронной обработки команд игроков (из C++ Game Server и Python Game Server).

6.  **Хранилище Данных Redis:** Используется модулем `user_service.py` в Python Auth gRPC Service и Python Auth TCP/JSON Service (в текущей реализации с `MOCK_USERS_DB`, полноценное использование Redis - концептуально) для хранения данных пользователей и сессий.

7.  **Система Мониторинга:**
    *   **Prometheus:** Сбор метрик со всех сервисов.
    *   **Grafana:** Визуализация метрик из Prometheus.

### Диаграмма Архитектуры (Mermaid)

```mermaid
graph TD
    subgraph Взаимодействие с пользователем
        UserClient[Игровой Клиент]
    end

    subgraph Шлюз / Балансировщик нагрузки
        Nginx[Nginx (Концептуальный/Опциональный для C++ сервисов)]
    end

    subgraph Сервисы Аутентификации
        CppTCPAUTH[C++ TCP Auth Server (компонент `auth_server_cpp`)]
        PythonAuthTCPJSON[Python Auth TCP/JSON Service (на базе `auth_server.main`)]
        PythonAuthGRPC[Python Auth gRPC Service (на базе `auth_server.auth_grpc_server`)]
    end

    subgraph Сервисы Игровой Логики
        CppGameServer[C++ Game Server (компонент `game_server_cpp`)]
        PlayerCommandHandler[C++ Player Command Consumer (часть C++ Game Server)]
        PythonGameServer[Python Game Server (Python Игровой Сервис, на базе `game_server.main`)]
    end
    
    subgraph Брокеры сообщений
        KafkaAuth[Kafka (auth_events)]
        KafkaGame[Kafka (game_events, session_history, tank_coords)]
        RabbitMQCommands[RabbitMQ (player_commands)]
    end

    subgraph Хранилища данных
        Redis[Redis (Пользовательские данные, Сессии - концептуально для Python)]
    end

    subgraph Мониторинг
        Prometheus[Prometheus]
        Grafana[Grafana]
    end

    UserClient -->|TCP/UDP Игровой трафик, TCP Трафик аутентификации (через Nginx для C++)| Nginx
    UserClient -->|TCP/UDP Игровой трафик (напрямую или через Nginx)| PythonGameServer

    Nginx -->|TCP Трафик аутентификации (Порт 9000)| CppTCPAUTH
    Nginx -->|TCP Игровой трафик (Порт 8888)| CppGameServer
    Nginx -->|UDP Игровой трафик (Порт 8889)| CppGameServer

    CppTCPAUTH -->|gRPC: Аутентификация/Регистрация пользователя| PythonAuthGRPC
    
    PythonAuthGRPC -->|CRUD: Учетные данные пользователя (MOCK_USERS_DB)| Redis
    PythonAuthGRPC -->|Pub: События аутентификации (концептуально)| KafkaAuth

    PythonAuthTCPJSON -->|CRUD: Учетные данные пользователя (MOCK_USERS_DB)| Redis
    PythonAuthTCPJSON -->|Pub: События аутентификации (концептуально)| KafkaAuth


    CppGameServer -->|gRPC: Валидация сессионного токена (через AuthenticateUser)| PythonAuthGRPC
    CppGameServer -->|Pub: Команда игрока| RabbitMQCommands
    PlayerCommandHandler -.->|Sub: Читает команду игрока| RabbitMQCommands
    PlayerCommandHandler -->|Exec: Применяет команду к состоянию игры| CppGameServer
    CppGameServer -->|Pub: Игровые события, История сессий, Координаты танка| KafkaGame

    PythonGameServer -->|TCP/JSON Аутентификация| PythonAuthTCPJSON
    PythonGameServer -->|Pub: Команда игрока| RabbitMQCommands
    PythonGameServer -->|Pub: Игровые события (концептуально)| KafkaGame
    
    Prometheus -->|Собирает метрики| CppTCPAUTH
    Prometheus -->|Собирает метрики| PythonAuthGRPC
    Prometheus -->|Собирает метрики| PythonAuthTCPJSON
    Prometheus -->|Собирает метрики| CppGameServer
    Prometheus -->|Собирает метрики| PythonGameServer
    Prometheus -->|Собирает метрики| KafkaGame
    Prometheus -->|Собирает метрики| RabbitMQCommands
    Grafana -->|Запрашивает метрики| Prometheus
```

## Детальное Описание Сервисов

### 1. Сервисы Аутентификации (Python)

Компоненты Python, отвечающие за аутентификацию пользователей. Существуют две основные реализации (gRPC и TCP/JSON), использующие общий модуль `auth_server/user_service.py` для управления данными пользователей.

*Примечание о Nginx: В базовой конфигурации `docker-compose.yml` Nginx не включен и не является обязательным для запуска C++ сервисов напрямую. Его использование (например, через конфигурацию `deployment/nginx/nginx.conf`) является опциональным и предусмотрено для более продвинутых сценариев развертывания, таких как SSL-терминация, балансировка нагрузки или проксирование в Kubernetes.*

#### Общий компонент: `auth_server/user_service.py`

*   **Роль**: Модуль для управления данными пользователей.
*   **Хранилище данных**: Использует словарь в памяти (`MOCK_USERS_DB`) для хранения учетных данных. `MOCK_USERS_DB` хранит **сырые пароли** для предустановленных пользователей (например, `user1:password123`).
*   **Ключевые функции**:
    *   `authenticate_user(username, password)`: Сравнивает предоставленный **сырой пароль** с паролем, хранящимся в `MOCK_USERS_DB`.
    *   `create_user(username, password_hash)`: Сохраняет предоставленный **хеш пароля** в `MOCK_USERS_DB`.
*   **Несоответствие логики и ограничения**:
    *   `UserService.create_user` (вызываемый из gRPC сервиса `RegisterUser`) сохраняет **хешированный пароль**.
    *   `UserService.authenticate_user` (используемый обоими сервисами аутентификации: gRPC `AuthenticateUser` и TCP/JSON `login`) сравнивает предоставленный **сырой пароль** с сохраненным значением в `MOCK_USERS_DB`.
    *   **Следствие**: Новые пользователи, зарегистрированные через gRPC сервис, не смогут быть аутентифицированы через `UserService.authenticate_user`, так как для них в `MOCK_USERS_DB` будет храниться хеш, а `authenticate_user` ожидает сырой пароль для сравнения (или, если бы он хешировал входящий пароль, ему нужна была бы соль, которая не сохраняется отдельно). Аутентификация успешна только для предустановленных пользователей с сырыми паролями в `MOCK_USERS_DB`.
*   **Интеграция с Redis**:
    *   Функция `initialize_redis_client()` является заглушкой и не устанавливает реальное соединение или взаимодействие с Redis.
    *   Реальная интеграция с Redis для хранения пользовательских данных или сессий в `user_service.py` отсутствует.

#### A. Python Auth gRPC Service (на базе `auth_server.auth_grpc_server`)

*   **Точка входа**: `python -m auth_server.auth_grpc_server`.
*   **Назначение и роль**: Основной сервис аутентификации для C++ компонентов.
*   **API (gRPC)**:
    *   `rpc AuthenticateUser(AuthRequest) returns (AuthResponse)`:
        *   Логика: Вызывает `user_service.authenticate_user(username, raw_password)`.
        *   Сессионный токен: При успешной аутентификации в качестве токена возвращается **имя пользователя** (`response.token = request.username`).
    *   `rpc RegisterUser(AuthRequest) returns (AuthResponse)`:
        *   Логика: Хеширует сырой пароль из `AuthRequest` и вызывает `user_service.create_user(username, hashed_password)`.
*   **Взаимодействие с `user_service.py`**: Подтверждено, использует `user_service.authenticate_user` и `user_service.create_user`.
*   **Зависимости и конфигурация**:
    *   Переменные окружения для Redis (`REDIS_HOST`, `REDIS_PORT`) и Kafka (`KAFKA_BOOTSTRAP_SERVERS`) присутствуют в коде, но эти системы **не используются** для основной логики сервиса (аутентификация/регистрация через `MOCK_USERS_DB`, события Kafka не публикуются).
*   **Dockerfile**: `auth_server/Dockerfile` используется для сборки Docker-образа, который запускает этот сервис.

#### B. Python Auth TCP/JSON Service (на базе `auth_server.main` и `auth_server.tcp_handler.py`)

*   **Точка входа**: `python -m auth_server.main`.
*   **Назначение и роль**: Альтернативный сервис аутентификации для Python Game Server.
*   **API (TCP/JSON)** (логика в `auth_server/tcp_handler.py`):
    *   `login`: Подтверждено, использует `user_service.authenticate_user(username, raw_password)`.
    *   `register`: Обработчик `register` в `tcp_handler.py` **не вызывает** `user_service.create_user`. Он возвращает mock-ответ `{"status": "success", "message": "User registered (mock)"}`. Фактическая регистрация нового пользователя через этот сервис **не происходит**.
*   **Взаимодействие с `user_service.py`**: Использует `UserService.authenticate_user()`.
*   **Метрики (`auth_server/metrics.py`)**:
    *   Предоставляет метрики для Prometheus.
    *   HTTP сервер метрик запускается на порту `8000`.
*   **Конфигурационные параметры**: Настраивается через переменные окружения.

### 2. C++ TCP Auth Server (`auth_server_cpp`)

*   **Назначение и роль**: Внешний интерфейс для клиентов, проксирующий запросы к Python Auth gRPC Service.
*   **Протоколы**:
    *   Принимает JSON от клиента по TCP.
    *   Проксирует запросы (транслирует JSON в gRPC) к Python Auth gRPC Service. (Это подтверждено).
*   **Точка входа**: `main_auth.cpp`.

### 3. Python Game Server (на базе `game_server.main`)

*   **Точка входа**: `python -m game_server.main`.
*   **Назначение и роль**: Python реализация игрового сервера.
*   **Взаимодействие с другими сервисами**:
    *   **Аутентификация**: Использует `AuthClient` (`game_server/auth_client.py`) для связи с **Python Auth TCP/JSON Service**.
    *   **RabbitMQ**: Публикует команды `move` и `shoot`.
    *   **Kafka**: Публикация игровых событий в Kafka из этого сервиса **не реализована**.
*   **Конфигурационные параметры**: Настраивается через переменные окружения.

### 4. C++ Game Server (`game_server_cpp`)

*   **Назначение и роль**: Высокопроизводительный игровой сервер на C++.
*   **Валидация сессии (токена)**:
    *   Для валидации сессии (токена), полученного от клиента, C++ Game Server вызывает gRPC метод `AuthenticateUser` на Python Auth gRPC Service.
    *   В запросе `AuthRequest` к `AuthenticateUser`:
        *   Поле `password` используется для передачи самого **токен**а (который изначально является именем пользователя).
        *   Поле `username` используется для передачи **имени пользователя**, ассоциированного с этим токеном.
    *   **Это нестандартный способ валидации сессии.** Отдельного RPC для валидации токена (например, `ValidateSessionToken`) в `auth_service.proto` нет. Python Auth gRPC Service, получая такой запрос, пытается выполнить `user_service.authenticate_user(username, token_as_password)`, что будет успешно только если `token_as_password` совпадет с сырым паролем пользователя в `MOCK_USERS_DB`, что не является корректной логикой валидации токена.
*   **Остальное описание**: (Совпадает с существующим в README) ...

### 5. Общие Python Модули (`core`)

*   **`core/config.py`**:
    *   **Роль**: Предполагается для централизованной конфигурации.
    *   **Текущее состояние**: Подтверждено, его использование для централизованной конфигурации пока **не реализовано**. Файл существует, но не содержит общих настроек.
*   **`core/message_broker_clients.py`**:
    *   `RabbitMQClient`: Используется Python Game Server.
    *   `KafkaClient`: Содержит базовую реализацию Kafka producer. Подтверждено, Python-сервисы его активно **не используют** для публикации сообщений.
*   **`core/redis_client.py`**:
    *   `get_redis_client`: Функция для создания клиента Redis.
    *   **Использование**: Подтверждено, активно **не используется** Python Auth сервисами из-за применения `MOCK_USERS_DB` в `auth_server.user_service`.

### Инфраструктурные Компоненты (Kafka, RabbitMQ, Redis, Prometheus & Grafana, Nginx)
(Описание этих компонентов остается прежним)

## Структура каталогов

*   `auth_server/`: Исходный код Python сервисов аутентификации.
    *   `auth_grpc_server.py`: Основной скрипт запуска Python Auth gRPC Service.
    *   `main.py`: Точка входа для Python Auth TCP/JSON Service.
    *   `tcp_handler.py`: Обработчик TCP-соединений для Python Auth TCP/JSON сервиса.
    *   `user_service.py`: Модуль для работы с данными пользователей (в настоящее время использует mock-базу).
    *   `metrics.py`: Определения метрик Prometheus для Python Auth TCP/JSON сервиса.
    *   `grpc_generated/`: Содержит Python код (`*_pb2.py`, `*_pb2_grpc.py`), сгенерированный из `.proto` файлов для gRPC сервиса. Копируется из `protos/generated/python/` при сборке Docker-образа Python Auth gRPC Service.
    *   `Dockerfile`: Dockerfile для сборки образа Python Auth сервиса. Может быть использован для запуска как Python Auth gRPC Service, так и Python Auth TCP/JSON Service, в зависимости от команды запуска контейнера (CMD).

*   `core/`: Общие модули Python, используемые различными Python-сервисами.
    *   `config.py`: Модуль для общих конфигурационных параметров (например, настройки логирования).
    *   `message_broker_clients.py`: Клиенты для Kafka и RabbitMQ (например, `RabbitMQClient` используется Python Game Server).
    *   `redis_client.py`: Клиент для Redis (несмотря на наличие, `user_service.py` в `auth_server` пока не использует Redis для данных пользователей).

*   `cpp/`: Корневая директория для всех C++ компонентов, включая их исходный код, CMake-скрипты и общий Dockerfile для сборки.
    *   `auth_server_cpp/`: Исходный код C++ TCP Auth Server. Принимает запросы от клиентов и проксирует их через gRPC к Python Auth gRPC Service.
        *   `main_auth.cpp`: Точка входа.
        *   `auth_tcp_server.h/cpp`: Логика TCP сервера.
        *   `auth_tcp_session.h/cpp`: Логика обработки сессии клиента.
        *   `CMakeLists.txt`: Сборочный скрипт.
    *   `game_server_cpp/`: Исходный код C++ Game Server.
        *   `main.cpp`: Точка входа.
        *   `udp_handler.h/cpp`, `tcp_handler.h/cpp`, `tcp_session.h/cpp`: Обработчики сетевых протоколов.
        *   `command_consumer.h/cpp`: Компонент для чтения команд из RabbitMQ.
        *   `game_session.h/cpp`, `session_manager.h/cpp`, `tank.h/cpp`, `tank_pool.h/cpp`: Основная игровая логика.
        *   `kafka_producer_handler.h/cpp`: Обработчик для отправки сообщений в Kafka.
        *   `grpc_client.h/cpp`: Клиент для взаимодействия с Python Auth gRPC Service.
        *   `stubs.h/cpp`: Заглушки для функций, связанных с Kafka и RabbitMQ, что позволяет собирать и тестировать компоненты без их полной инициализации или для нужд тестирования.
        *   `CMakeLists.txt`: Сборочный скрипт.
    *   `protos/`: Содержит `.proto` файлы (например, `auth_service.proto`) и `CMakeLists.txt` для генерации gRPC и Protobuf кода для C++ (в `cpp/build/generated-sources/protobuf/`) и Python (в `protos/generated/python/`). Сгенерированный Python код затем копируется в `auth_server/grpc_generated/` при сборке Docker-образа Python Auth gRPC Service.
    *   `tests/`: Юнит-тесты для C++ компонентов (используют Catch2).
        *   `main_test.cpp`: Основной файл для запуска тестов.
        *   `test_*.cpp`: Файлы с тестовыми случаями.
        *   `CMakeLists.txt`: Сборочный скрипт для тестов.
    *   `CMakeLists.txt`: Корневой CMake-файл для сборки всех C++ проектов (включая сервисы, тесты и генерацию proto).
    *   `Dockerfile`: Общий Dockerfile для сборки C++ сервисов (C++ TCP Auth Server, C++ Game Server) и их зависимостей.

*   `deployment/`: Файлы, связанные с развертыванием.
    *   `docker-compose.yml`: Основной файл для оркестрации всех сервисов приложения (Python Auth gRPC Service, C++ TCP Auth Server, C++ Game Server, Kafka, RabbitMQ, Redis, и т.д.) в Docker.
    *   `nginx/nginx.conf`: Пример конфигурации Nginx (концептуально, не используется в `docker-compose.yml` по умолчанию).
    *   (Потенциально) Конфигурации Kubernetes.

*   `game_server/`: Исходный код Python игрового сервера. Альтернативная реализация игрового сервера, использующая Python Auth TCP/JSON сервис.
    *   `main.py`: Точка входа, запуск TCP/UDP обработчиков и сервера метрик.
    *   `udp_handler.py` (`GameUDPProtocol`): Логика UDP обработчика.
    *   `tcp_handler.py` (`handle_game_client`): Логика TCP обработчика.
    *   `game_logic.py` (`GameRoom`): Основная игровая логика для комнат.
    *   `auth_client.py` (`AuthClient`): Клиент для Python Auth TCP/JSON сервиса.
    *   `session_manager.py` (`SessionManager`): Управление игровыми сессиями.
    *   `tank_pool.py` (`TankPool`): Управление пулом танков.
    *   `models.py`: Модели данных (например, `Player`, `Tank`).
    *   `metrics.py`: Определения метрик Prometheus для Python игрового сервера.

*   `monitoring/`: Конфигурационные файлы для системы мониторинга.
    *   `prometheus/prometheus.yml`: Конфигурация Prometheus, включая цели для сбора метрик с сервисов.
    *   `grafana/provisioning/`: (Потенциально) Конфигурации дашбордов и источников данных Grafana.

*   `protos/`: Исходные файлы определения протоколов `.proto` (например, `auth_service.proto`). Эти файлы используются `cpp/protos/CMakeLists.txt` для генерации кода. Директория `protos/generated/python/` является местом вывода для сгенерированного Python кода.

*   `scripts/`: Вспомогательные скрипты.
    *   `run_servers.sh`: Скрипт для локального запуска Python Auth TCP/JSON Service и Python Game Server.
    *   `run_tests.sh`: Скрипт для запуска Python юнит- и интеграционных тестов.
    *   `send_tcp_test.py`: Скрипт для отправки тестовых TCP сообщений.
    *   `check_udp_bind.py`: Утилита для проверки доступности UDP порта.
    *   `test_script.sh`: Общий скрипт для различных тестовых задач.

*   `tests/`: Корневая директория для Python-ориентированных тестов.
    *   `load/`: Скрипты для нагрузочного тестирования Locust.
        *   `locustfile_auth.py`: Тестирует C++ TCP Auth Server.
        *   `locustfile_game.py`: Заготовка для тестирования C++ Game Server.
    *   `unit/`: Python юнит-тесты (например, `test_auth_service.py`, `test_user_service.py`).
    *   `test_integration.py`: Python интеграционные тесты (для Python-стека).
    *   `test_auth_server.py`, `test_game_server.py`: Дополнительные Python тесты для соответствующих Python Auth Service и Python Game Server.

*   `.dockerignore`: Указывает Docker, какие файлы и директории игнорировать при сборке образов Docker.
*   `Dockerfile`: Корневой Dockerfile. Его назначение - сборка базового окружения для Python-приложений, включая установку зависимостей из `requirements.txt`. Он может использоваться для запуска Python скриптов или как основа для других Docker-образов Python-сервисов, если они не имеют собственного Dockerfile.
*   `pyproject.toml`: Файл конфигурации для Python проектов, часто используется для управления зависимостями и сборкой с помощью инструментов, таких как Poetry, Flit или для настройки линтеров/форматтеров типа `black` или `ruff`.
*   `requirements.txt`: Список Python зависимостей для всего проекта.
*   `README.md`: Этот файл.

## Потоки данных

### Регистрация пользователя (через C++ TCP Auth Server)
1.  **Клиент -> Nginx (концептуально) -> C++ TCP Auth Server (компонент `auth_server_cpp`):** Клиент отправляет TCP-запрос с данными для регистрации (например, логин, пароль в JSON-формате: `{"action": "register", "username": "user", "password": "pwd"}`). Nginx (если используется) проксирует этот запрос на C++ TCP Auth Server.
2.  **C++ TCP Auth Server -> Python Auth gRPC Service (сервис на базе `auth_server.auth_grpc_server`):** C++ TCP Auth Server парсит JSON, формирует gRPC-запрос `RegisterUser` (содержащий сырой логин и пароль) и отправляет его в Python Auth gRPC Service.
3.  **Python Auth gRPC Service:**
    *   Получает запрос `RegisterUser`.
    *   Хеширует пароль с использованием `pbkdf2_sha256` (из `passlib`).
    *   Вызывает `user_service.create_user(username, password_hash)`.
    *   `auth_server.user_service.py` (через `create_user`) сохраняет `username` и **хеш пароля** (`password_hash`) в `MOCK_USERS_DB`. Проверка на существующего пользователя перед сохранением зависит от реализации в `create_user`.
    *   *Использование Redis*: `user_service.py` на данный момент не использует Redis для хранения пользователей; `initialize_redis_client()` является заглушкой.
    *   *Публикация в Kafka*: Публикация события `user_registered` в топик `auth_events` из Python Auth gRPC Service на данный момент не реализована или является концептуальной.
    *   Формирует gRPC-ответ (`AuthResponse` с сообщением об успехе или ошибке) и отправляет его обратно в C++ TCP Auth Server.
4.  **C++ TCP Auth Server -> Клиент:** C++ TCP Auth Server транслирует ответ от Python Auth gRPC Service клиенту по TCP в JSON-формате.

### Вход пользователя и начало игры (через C++ Game Server)
1.  **Клиент -> Nginx (концептуально) -> C++ TCP Auth Server (компонент `auth_server_cpp`):** Клиент отправляет TCP-запрос с учетными данными (логин, пароль в JSON: `{"action": "login", "username": "user", "password": "pwd"}`) для входа.
2.  **C++ TCP Auth Server -> Python Auth gRPC Service (сервис на базе `auth_server.auth_grpc_server`):** C++ TCP Auth Server формирует gRPC-запрос `AuthenticateUser` (с сырым логином и паролем) и отправляет его в Python Auth gRPC Service.
3.  **Python Auth gRPC Service:**
    *   Получает запрос `AuthenticateUser`.
    *   Вызывает `user_service.authenticate_user(username, password)`.
    *   `auth_server.user_service.py` сравнивает предоставленный **сырой пароль** (`password`) с паролем, хранящимся в `MOCK_USERS_DB`. Это будет работать для предустановленных пользователей (если их пароли сохранены в сыром виде), но **не будет работать для пользователей, зарегистрированных через gRPC-метод `RegisterUser`**, так как для них в `MOCK_USERS_DB` сохранен хеш пароля, а не сырой пароль.
    *   В случае успеха, в `auth_grpc_server.py` в качестве сессионного токена используется имя пользователя (`token = request.username`).
    *   *Сохранение сессионного токена в Redis*: Нереализовано; `user_service.py` и `auth_grpc_server.py` не управляют сессиями в Redis.
    *   *Публикация `user_loggedin` в Kafka*: Концептуально/нереализовано для Python Auth gRPC Service.
    *   Возвращает gRPC-ответ (`AuthResponse` с токеном (именем пользователя) в случае успеха, или сообщением об ошибке).
4.  **C++ TCP Auth Server -> Клиент:** Передает клиенту сессионный токен (имя пользователя) или сообщение об ошибке в JSON-формате.
5.  **Клиент -> Nginx (концептуально) -> C++ Game Server (компонент `game_server_cpp`):** Клиент, получив токен, устанавливает новое TCP (или UDP) соединение с C++ Game Server, передавая этот токен для "входа в игру" или последующей валидации команд.
6.  **C++ Game Server -> Python Auth gRPC Service (сервис на базе `auth_server.auth_grpc_server`):** Для валидации токена C++ Game Server вызывает gRPC метод `AuthenticateUser` на Python Auth gRPC Service, передавая токен в поле `password` и имя пользователя в поле `username`. *Примечание: Это нестандартный способ валидации сессии; специализированный RPC `ValidateSessionToken` в `auth_service.proto` отсутствует.*
7.  **Python Auth gRPC Service (при "валидации" токена):**
    *   Вызывается `user_service.authenticate_user(username, token_as_password)`, где `username` – это имя пользователя, а `token_as_password` – это токен (который также является именем пользователя).
    *   **Проблемы с этим методом валидации**:
        *   Для пользователей, **зарегистрированных через gRPC**, в `MOCK_USERS_DB` хранится хеш их пароля. Сравнение `user_service.authenticate_user(username, username)` (так как токен = имя пользователя) с хешем пароля всегда завершится неудачей.
        *   Для **предустановленных пользователей** (с сырыми паролями в `MOCK_USERS_DB`), этот метод сработает только в том маловероятном случае, если их пароль случайно совпадает с их именем пользователя.
        *   Корректная валидация сессии (например, проверка токена в Redis с временем жизни) не реализована.
8.  **C++ Game Server:**
    *   Если "валидация" токена (некорректно) успешна: создает или присоединяет игрока к игровой сессии (`GameSession`), выделяет танк (`TankPool`).
    *   Сообщает клиенту об успешном входе.
    *   Публикует событие `player_joined_session` в Kafka (топик `player_sessions_history`) через `KafkaProducerHandler`.

### Вход пользователя и начало игры (через Python Game Server)
1.  **Клиент -> Python Game Server (сервис на базе `game_server.main`, TCP Handler):** Клиент отправляет TCP-запрос вида `LOGIN <username> <password>`.
2.  **Python Game Server (TCP Handler) -> `GameRoom`:** Обработчик TCP (`handle_game_client`) вызывает `game_room.authenticate_player(username, password)`.
3.  **`GameRoom` -> `AuthClient`:** `GameRoom` использует `auth_client.login_user(username, password)`.
4.  **`AuthClient` (`game_server/auth_client.py`) -> Python Auth TCP/JSON Service (сервис на базе `auth_server.main`):**
    *   `AuthClient` подключается к Python Auth TCP/JSON Service (например, `localhost:8888`) и отправляет JSON: `{"action": "login", "username": "user1", "password": "password123"}`.
5.  **Python Auth TCP/JSON Service (`auth_server.tcp_handler.py`):**
    *   Вызывает `user_service.authenticate_user(username, password)`.
    *   `user_service.py` сравнивает предоставленный **сырой пароль** с паролем, хранящимся в `MOCK_USERS_DB`. Этот метод аутентификации будет работать для предустановленных пользователей, чьи пароли сохранены в сыром виде.
    *   Возвращает JSON-ответ (`AuthClient`): `{"status": "success/failure", ..., "token": "username"}`.
6.  **`AuthClient` -> `GameRoom`:** Возвращает результат аутентификации.
7.  **`GameRoom` -> Python Game Server (TCP Handler):** Возвращает результат.
8.  **Python Game Server (TCP Handler):**
    *   При успехе: создает `Player`, добавляет в `GameRoom`.
    *   Отправляет клиенту `LOGIN_SUCCESS` или `LOGIN_FAILURE`.
    *   Дальнейшее взаимодействие (выделение танка) через `SessionManager` и `TankPool`.

### Отправка команды игроком (например, движение, через C++ Game Server)
1.  **Клиент -> Nginx (концептуально) -> C++ Game Server (компонент `game_server_cpp`):** Клиент отправляет UDP/TCP пакет с командой (например, `{"command": "move", "tank_id": 1, "details": {"x": 10, "y": 20}}`).
2.  **C++ Game Server (UDP/TCP Handler):** Принимает сообщение, формирует JSON и публикует в очередь `player_commands` в RabbitMQ.
3.  **C++ Player Command Consumer (часть C++ Game Server):** Читает команды из RabbitMQ.
4.  **C++ Player Command Consumer:** Находит сессию (`GameSession`) и танк (`Tank`).
5.  **C++ Player Command Consumer:** Вызывает метод у объекта танка (например, `tank->move(new_position)`).
6.  **C++ Game Server (GameSession/Tank):** Уведомляет других клиентов об изменении состояния (например, по UDP).
7.  **C++ Game Server (KafkaProducerHandler):** Публикует событие (например, `tank_moved`) в Kafka (например, топик `tank_coordinates_history`).

### Отправка команды игроком (например, движение, через Python Game Server)
1.  **Клиент -> Python Game Server (сервис на базе `game_server.main`, UDP Handler или TCP Handler):**
    *   **UDP (`game_server.udp_handler`):** JSON: `{"action": "move", "player_id": "user1", "tank_id": "tankA", "position": [10,20]}`.
    *   **TCP (`game_server.tcp_handler`):** Текстовая команда: `MOVE 10 20`.
2.  **Python Game Server (UDP/TCP Handler):**
    *   Принимает и парсит сообщение.
    *   Для `MOVE` или `SHOOT` формирует JSON для RabbitMQ. Например: `{"player_id": "user1", "command": "move", ...}`.
    *   Публикует сообщение в очередь `player_commands` в RabbitMQ через `RabbitMQClient` (`core.message_broker_clients`).
3.  **Сообщение в RabbitMQ ожидает обработки консьюмером:**
    *   Основной консьюмер для `player_commands` — это **C++ Player Command Consumer** (часть C++ Game Server). Таким образом, команды от Python Game Server будут обрабатываться C++ логикой, так как отдельного Python консьюмера для команд, опубликованных из Python Game Server, не существует.
    *   Если предполагается отдельный Python консьюмер для команд, опубликованных Python Game Server, его разработка и интеграция потребуются дополнительно.

### Общие замечания по Data Flows:
*   **Хранение пользовательских данных и сессий (Python сервисы):** Подтверждено: Python компоненты (Python Auth TCP/JSON Service, Python Auth gRPC Service и, следовательно, Python Game Server) в настоящее время используют `MOCK_USERS_DB` (словарь в памяти) через `auth_server.user_service.py`. Реальное использование Redis для хранения пользовательских данных или активных сессий не реализовано.
*   **Публикация событий в Kafka (Python сервисы):** Подтверждено: Публикация событий из Python компонентов в Kafka (события аутентификации из Python Auth Services, игровые события из Python Game Server) на данный момент не реализована или является концептуальной. C++ Game Server (компонент `game_server_cpp`) реализует публикацию игровых событий в Kafka.

## Требования

### Общие требования
*   **Git:** Система контроля версий для клонирования репозитория.
*   **Docker & Docker Compose:** Для сборки и запуска контейнеризированных сервисов и самого приложения. Версия Docker Compose должна поддерживать формат `docker-compose.yml` версии 3.8+.

### Разработка на Python
*   **Python:** Рекомендуется версия 3.9 или новее. Убедитесь, что Python добавлен в `PATH`.
*   **PIP:** Менеджер пакетов Python (обычно устанавливается вместе с Python).
*   **Виртуальное окружение (Рекомендуется):** Использование `venv` или `conda` для изоляции зависимостей проекта.
*   **Зависимости Python:** Полный список указан в файле `requirements.txt`. Ключевые библиотеки для работы проекта и **разработки/тестирования**:
    *   `grpcio`, `grpcio-tools`: для gRPC.
    *   `redis`: для взаимодействия с Redis.
    *   `confluent-kafka`: для взаимодействия с Kafka.
    *   `pika`: для взаимодействия с RabbitMQ.
    *   `prometheus_client`: для метрик Prometheus.
    *   `passlib[bcrypt]`: для хеширования паролей.
    *   `pytest`, `pytest-asyncio`: для написания и запуска модульных тестов.
    *   `locust`: для нагрузочного тестирования.

### Разработка на C++
Для разработки C++ компонентов потребуется настроенное окружение.

*   **Компилятор C++:** Поддерживающий стандарт C++17 (например, GCC 8+, Clang 6+, MSVC Visual Studio 2019+).
*   **CMake:** Система автоматизации сборки.
    *   Локальная сборка: версия 3.16 или новее.
    *   Docker-сборка: используется версия CMake >= 3.29 (например, 3.29.6, как указано в `cpp/Dockerfile`) из-за использования политики `CMP0167`.
*   **`protoc` (Компилятор Protocol Buffers) и `grpc_cpp_plugin` (Плагин gRPC C++):**
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

## Установка

### 1. Клонирование репозитория
```bash
git clone <URL_вашего_репозитория> # Замените на URL вашего репозитория
cd <имя_каталога_проекта>
```

### 2. Настройка окружения Python
Рекомендуется использовать виртуальное окружение.
```bash
# Создание (например, python3 -m venv venv) и активация (source venv/bin/activate или .\venv\Scripts\activate)
pip install -r requirements.txt
```

### 3. Установка зависимостей C++
Следуйте инструкциям в разделе [Разработка на C++](#разработка-на-c) для установки зависимостей с помощью `vcpkg` или системного менеджера пакетов.

### 4. Генерация gRPC кода

*   **Для C++:** Код генерируется автоматически во время CMake конфигурации/сборки проекта (цель `proto_lib` в `cpp/protos/CMakeLists.txt`). Убедитесь, что `protoc` и `grpc_cpp_plugin` доступны вашей системе сборки (обычно решается через `vcpkg` или установку соответствующих dev-пакетов).
*   **Для Python:** Сгенерированные файлы (`*_pb2.py`, `*_pb2_grpc.py`) должны находиться в `protos/generated/python/`. Если их нет или требуется обновление:
    1.  Убедитесь, что установлены `grpcio-tools`: `pip install grpcio-tools`
    2.  Из корневой директории проекта выполните команду (при необходимости создайте директорию `protos/generated/python`):
        ```bash
        python -m grpc_tools.protoc -I./protos --python_out=./protos/generated/python --pyi_out=./protos/generated/python --grpc_python_out=./protos/generated/python ./protos/auth_service.proto
        ```
        *Примечание: Docker-сборка для `auth_server` (`auth_server/Dockerfile`) ожидает, что эти файлы уже сгенерированы и будут скопированы из `protos/generated/python` в образ.*

### 5. Сборка компонентов C++
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

## Запуск приложения

### Через Docker Compose (Рекомендуемый способ)
*Примечание: Если были внесены изменения в `requirements.txt` (Python-зависимости) или исходный код Python/C++ сервисов, используйте опцию `--build` при запуске (`docker compose up --build`) для пересборки Docker-образов.*
Это основной способ для запуска всего стека приложения, включая все C++ и Python сервисы, а также инфраструктурные компоненты (Kafka, RabbitMQ, Redis, Zookeeper, Prometheus, Grafana).
`docker-compose.yml` настроен для запуска следующей конфигурации:
*   **C++ TCP Auth Server (`cpp_auth_server`)**: Слушает на порту `9000` (маппинг `9000:9000`), взаимодействует с `python_auth_grpc_service`.
*   **Python Auth gRPC Service (`python_auth_grpc_service`)**: Запускается из `auth_server/Dockerfile` с командой `python -m auth_server.auth_grpc_server`. Слушает gRPC запросы на порту `50051` внутри Docker-сети. Наружу не маппится напрямую, так как с ним общается `cpp_auth_server`.
*   **C++ Game Server (`cpp_game_server`)**: Слушает на TCP порту `8888` (маппинг `8888:8888`) и UDP порту `8889` (маппинг `8889:8889`). Взаимодействует с `python_auth_grpc_service` для валидации сессий.
*   **Инфраструктурные сервисы**: Kafka (порт `29092`), RabbitMQ (порты `5672`, `15672`), Redis (порт `6379`), Zookeeper, Prometheus (порт `9090`), Grafana (порт `3000`).

*Примечание: Python Auth TCP/JSON Service и Python Game Server по умолчанию не запускаются через `docker-compose.yml`. Для их запуска используйте локальные методы или адаптируйте `docker-compose.yml`.*

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
Этот способ может быть полезен для разработки и отладки отдельных сервисов. Требует, чтобы все зависимые инфраструктурные компоненты (Kafka, RabbitMQ, Redis) были запущены и доступны (например, через `docker compose up` только для них, или установлены локально).

#### Python сервисы аутентификации (`auth_server/`)

*   **A. Python Auth gRPC Service (`auth_server.auth_grpc_server`)**
    *   **Назначение**: Сервис аутентификации для C++ компонентов.
    *   **Предварительно**: Активируйте Python виртуальное окружение (`source venv/bin/activate` или `.\venv\Scripts\activate`).
    *   **Команда запуска** (из корневой директории проекта):
        ```bash
        python -m auth_server.auth_grpc_server
        ```
    *   **Порт**: Слушает gRPC запросы на порту `50051`.
    *   **Хранилище данных**: Использует `user_service.py`, который работает с `MOCK_USERS_DB` (словарь в памяти). Redis и Kafka не используются активно для хранения данных или публикации событий в этой конфигурации.
    *   **Зависимости**: Не требует внешних сервисов для базовой работы с `MOCK_USERS_DB`.

*   **B. Python Auth TCP/JSON Service (`auth_server.main`)**
    *   **Назначение**: Сервис аутентификации для Python Game Server.
    *   **Предварительно**: Активируйте Python виртуальное окружение.
    *   **Команда запуска** (из корневой директории проекта):
        ```bash
        python -m auth_server.main
        ```
        Или через переменные окружения для кастомизации:
        ```bash
        AUTH_SERVER_HOST=0.0.0.0 AUTH_SERVER_PORT=8888 PROMETHEUS_PORT_AUTH=8000 python -m auth_server.main
        ```
    *   **Порты**:
        *   TCP сервер для логина/регистрации: по умолчанию `0.0.0.0:8888`.
        *   HTTP сервер метрик Prometheus: по умолчанию `0.0.0.0:8000`.
    *   **Хранилище данных**: Использует `user_service.py` с `MOCK_USERS_DB`.
    *   **Зависимости**: Не требует внешних сервисов для базовой работы с `MOCK_USERS_DB`.

#### Python игровой сервер (`game_server.main`)
*   **Назначение**: Python реализация игрового сервера.
*   **Предварительно**:
    *   Активируйте Python виртуальное окружение.
    *   Убедитесь, что **Python Auth TCP/JSON Service (`auth_server.main`)** запущен и доступен.
    *   Убедитесь, что RabbitMQ запущен и доступен (для публикации команд).
*   **Переменные окружения** (пример):
    ```bash
    export GAME_SERVER_TCP_HOST=0.0.0.0
    export GAME_SERVER_TCP_PORT=8889
    export GAME_SERVER_UDP_HOST=0.0.0.0
    export GAME_SERVER_UDP_PORT=29998
    export AUTH_SERVER_HOST=localhost # Адрес запущенного Python Auth TCP/JSON Service
    export AUTH_SERVER_PORT=8888      # Порт Python Auth TCP/JSON Service
    export RABBITMQ_HOST=localhost    # Адрес RabbitMQ
    export RABBITMQ_PORT=5672
    export PROMETHEUS_PORT_GAME=8001
    ```
*   **Команда запуска** (из корневой директории проекта):
    ```bash
    python -m game_server.main
    ```
*   **Порты**:
    *   TCP сервер: по умолчанию `0.0.0.0:8889`.
    *   UDP сервер: по умолчанию `0.0.0.0:29998`.
    *   HTTP сервер метрик Prometheus: по умолчанию `0.0.0.0:8001`.
*   **Взаимодействие**:
    *   Использует `AuthClient` для связи с Python Auth TCP/JSON Service для аутентификации игроков.
    *   Публикует команды `move`/`shoot` в RabbitMQ.

#### C++ TCP сервер аутентификации (`auth_server_cpp`)
1.  Убедитесь, что **Python Auth gRPC Service (`auth_server.auth_grpc_server`)** запущен и доступен.
2.  Соберите проект C++ (см. раздел "Сборка компонентов C++").
3.  Запустите исполняемый файл (путь может отличаться, пример для Release сборки на Linux из `cpp/build/`):
    ```bash
    ./auth_server_cpp/auth_server_app --port 9000 --grpc_addr localhost:50051
    ```
    *   `--port 9000`: Порт, на котором C++ TCP Auth Server будет слушать клиентские подключения.
    *   `--grpc_addr localhost:50051`: Адрес и порт запущенного Python Auth gRPC Service.

#### C++ игровой сервер (`game_server_cpp`)
1.  Убедитесь, что **Python Auth gRPC Service (`auth_server.auth_grpc_server`)**, RabbitMQ и Kafka запущены и доступны.
2.  Соберите проект C++ (см. раздел "Сборка компонентов C++").
3.  Запустите исполняемый файл (путь может отличаться, пример для Release сборки на Linux из `cpp/build/`):
    ```bash
    ./game_server_cpp/game_server_app --tcp_port 8888 --udp_port 8889 \
    --rmq_host localhost --rmq_port 5672 --rmq_user user --rmq_pass password \
    --kafka_brokers localhost:29092 \
    --auth_grpc_host localhost --auth_grpc_port 50051
    ```
    *   `--tcp_port 8888`, `--udp_port 8889`: Порты игрового сервера.
    *   Параметры RabbitMQ (`--rmq_*`): Адрес, порт и учетные данные для RabbitMQ.
    *   `--kafka_brokers localhost:29092`: Адреса брокеров Kafka (порт `29092` если Kafka мапится на localhost из Docker, или `9092` если Kafka запущена локально без маппинга).
    *   `--auth_grpc_host localhost`, `--auth_grpc_port 50051`: Адрес и порт Python Auth gRPC Service для валидации сессий.

#### С использованием скрипта `scripts/run_servers.sh` (для Python сервисов)
Скрипт `./scripts/run_servers.sh` предоставляет удобный способ для одновременного запуска Python Auth TCP/JSON Service и Python Game Server, что полезно для разработки и тестирования чисто Python стека.

1.  **Назначение**:
    *   Запускает `auth_server.main` (Python Auth TCP/JSON Service) в фоновом режиме.
    *   Запускает `game_server.main` (Python Game Server) в фоновом режиме.
2.  **Запуск** (из корневой директории проекта):
    ```bash
    ./scripts/run_servers.sh start
    ```
    *   Скрипт установит переменные окружения для портов по умолчанию (Auth TCP/JSON: 8888, Game TCP: 8889, Game UDP: 29998, Prometheus метрики Auth: 8000, Game: 8001), если они не заданы.
    *   Логи каждого сервера будут перенаправлены в файлы `auth_server.log` и `game_server.log` в корневой директории проекта (поведение по умолчанию скрипта `run_servers.sh`).
    *   PID процессов сохраняются в `.auth_server.pid` и `.game_server.pid`.
3.  **Просмотр логов**:
    ```bash
    tail -f auth_server.log
    tail -f game_server.log
    ```
4.  **Остановка серверов**:
    ```bash
    ./scripts/run_servers.sh stop
    ```
    Эта команда прочитает PID из `.pid` файлов и завершит соответствующие процессы.
5.  **Статус серверов**:
    ```bash
    ./scripts/run_servers.sh status
    ```

*Примечание: Адаптируйте хосты и порты в командах и переменных окружения в зависимости от того, как и где у вас запущена инфраструктура (например, локально или в Docker).*

## Стратегия тестирования и окружения

В проекте применяется многоуровневая стратегия тестирования для обеспечения качества и надежности различных компонентов системы. Тестирование проводится в различных окружениях, чтобы максимально покрыть возможные сценарии использования.

### Окружения для тестирования:

*   **Локальное окружение разработчика (Windows/Linux/macOS):**
    *   Используется для разработки и частого запуска юнит-тестов (C++ и Python).
    *   C++ компоненты собираются с помощью системного компилятора и CMake (с `vcpkg` для управления C++ зависимостями, особенно рекомендуется для Windows).
    *   Python тесты запускаются в виртуальном окружении.
    *   Инфраструктурные зависимости (Kafka, RabbitMQ, Redis) для Python интеграционных или нагрузочных тестов могут быть запущены локально через Docker Compose (запуская только эти зависимости).

*   **Docker-окружение (через `docker-compose.yml`):**
    *   Основное окружение для запуска полного стека C++ сервисов, Python gRPC Auth сервиса и инфраструктурных компонентов. Используется для ручного тестирования взаимодействия C++ компонентов и для нагрузочного тестирования C++ сервисов.
    *   `cpp/Dockerfile` используется для сборки C++ сервисов.
    *   `auth_server/Dockerfile` используется для Python Auth gRPC сервиса.
    *   C++ юнит-тесты могут быть выполнены внутри builder-стадии Docker-образа C++ сервисов или путем запуска тестового исполняемого файла в работающем контейнере.

### Типы тестов:

1.  **C++ Юнит-тесты:**
    *   **Цель:** Проверка корректности отдельных модулей и классов C++ кода.
    *   **Инструменты:** Catch2.
    *   **Окружение:** Локально или в Docker. Не требуют внешних зависимостей (используют mock-объекты).

*   **Python Юнит-тесты:**
    *   **Цель:** Проверка отдельных модулей, классов и функций Python-сервисов. Для `auth_server` и `game_server` реализовано значительное покрытие модульными тестами, включая все основные компоненты:
        *   `auth_server`: `user_service.py`, `tcp_handler.py`, `auth_grpc_server.py`, `main.py` (метрики).
        *   `game_server`: `auth_client.py`, `game_logic.py` (`GameRoom`), `tank.py`, `tank_pool.py`, `session_manager.py`, `tcp_handler.py`, `udp_handler.py`. Также протестирована интеграция метрик (`ACTIVE_SESSIONS`, `TANKS_IN_USE`) в соответствующие модули.
    *   **Инструменты:** `pytest`, `pytest-asyncio`, `unittest.mock`.
    *   **Окружение:** Локально. Внешние сервисы и зависимости (например, Kafka, gRPC-сервисы, другие компоненты проекта) мокаются для обеспечения изоляции тестов.
    *   **Расположение**: `tests/unit/`.

3.  **Python Интеграционные тесты:**
    *   **Цель:** Проверка взаимодействия между Python сервисами (`auth_server` (TCP/JSON) и `game_server`), включая их подключение к RabbitMQ (если используется `RabbitMQClient` в тестах) или другим мокам/реальным зависимостям, доступным локально.
    *   **Инструменты:** `pytest`, `pytest-asyncio`.
    *   **Окружение:** Локально. Могут требовать запущенных Python Auth TCP/JSON Service и Python Game Server (например, через `scripts/run_servers.sh`) и, возможно, локально доступных брокеров сообщений (если тесты их используют напрямую). *Не требуют полного стека Docker Compose с C++ сервисами.*

4.  **Нагрузочные тесты:**
    *   **Цель:** Оценка производительности и стабильности ключевых сервисов.
    *   **Инструменты:** Locust.
    *   **Окружение:**
        *   Для `locustfile_auth.py` (тестирование C++ TCP Auth Server): Требуется запущенный стек через `docker compose up`, так как он тестирует `cpp_auth_tcp_server` (порт 9000), который проксирует на `python_auth_grpc_service`.
        *   Для `locustfile_game.py` (тестирование C++ Game Server): Аналогично, требует `docker compose up`.

## Тестирование

Для запуска Python юнит-тестов и интеграционных тестов можно использовать скрипт `scripts/run_tests.sh` (расположен в директории `scripts/`).
Этот скрипт выполняет следующие действия:
1.  Устанавливает/обновляет зависимости из `requirements.txt` (если они еще не установлены).
2.  Запускает Python юнит-тесты из директории `tests/unit/` с помощью `pytest`.
3.  Запускает Python интеграционные тесты из файла `tests/test_integration.py` с помощью `pytest`.
Скрипт **не запускает** C++ юнит-тесты или нагрузочные тесты Locust.

### C++ Юнит-тесты

Юнит-тесты для C++ компонентов написаны с использованием фреймворка [Catch2](https://github.com/catchorg/Catch2) (v3.x).

**Расположение файлов:**
*   Исходный код тестов: `cpp/tests/`.
*   Основной файл для запуска тестов: `cpp/tests/main_test.cpp`.
*   Тестовые случаи: `cpp/tests/test_*.cpp`.

**Сборка тестов:**
*   Автоматически конфигурируются и собираются с помощью CMake при сборке C++ проекта (цель `game_tests`).
*   Исполняемый файл: `cpp/build/tests/[Release|Debug]/game_tests[.exe]`.

**Запуск тестов:**
Выполняются из каталога сборки C++ (например, `cpp/build/`).

1.  **Через CTest:**
    ```bash
    ctest -C Release  # Или Debug
    ctest -C Release -V # Подробный вывод
    ```
2.  **Напрямую:**
    *   Linux/macOS: `./tests/Release/game_tests [аргументы Catch2]`
    *   Windows: `.\tests\Release\game_tests.exe [аргументы Catch2]`
    *   Примеры аргументов: `--list-tests`, `[тег]`, `"название теста"`.

**Добавление новых тестов:**
1.  Создайте `test_my_feature.cpp` в `cpp/tests/`.
2.  Включите `#include "catch2/catch_all.hpp"` и заголовки тестируемого модуля.
3.  Пишите тесты, используя макросы Catch2.
4.  Добавьте `test_my_feature.cpp` в `cpp/tests/CMakeLists.txt` к цели `game_tests`.
5.  Пересоберите проект.

### Python Юнит-тесты

Модульные тесты для Python-компонентов написаны с использованием `pytest` и `pytest-asyncio` для асинхронного кода, а также `unittest.mock` для создания мок-объектов.

**Расположение файлов:**
*   Все Python юнит-тесты находятся в директории `tests/unit/`.
*   Тесты для `auth_server` включают: `test_auth_service.py`, `test_tcp_handler_auth.py`, `test_auth_grpc_server.py`, `test_auth_main.py`.
*   Тесты для `game_server` включают: `test_auth_client.py`, `test_game_logic.py`, `test_tank.py`, `test_tank_pool.py`, `test_session_manager.py`, `test_tcp_handler_game.py`, `test_udp_handler_game.py`.
*   Тесты для `core` компонентов будут добавлены в эту же директорию (например, `test_message_broker_clients.py`).

**Подготовка и Запуск:**
Команды выполняются из корневой директории проекта.
1.  Активируйте виртуальное окружение и установите зависимости (см. раздел [Requirements](#requirements) и [Installation](#installation)): `pip install -r requirements.txt`.
2.  Запуск всех Python юнит-тестов:
    ```bash
    pytest tests/unit/
    ```
    Или для более сокращенного вывода:
    ```bash
    python -m pytest tests/unit/
    ```
3.  Для запуска тестов в конкретном файле:
    ```bash
    pytest tests/unit/test_my_module.py
    ```
4.  Для запуска конкретного теста по имени (или части имени) с использованием маркера `-k`:
    ```bash
    pytest tests/unit/test_my_module.py -k "test_function_name_substring"
    ```
Скрипт `scripts/run_tests.sh` также должен запускать эти тесты (необходимо проверить и при необходимости обновить его содержимое).

**Добавление новых тестов:**
1.  Создайте файл с префиксом `test_` (например, `test_my_new_module.py`) в директории `tests/unit/`.
2.  Пишите тестовые функции с префиксом `test_` или тестовые классы с префиксом `Test`.
3.  `pytest` автоматически обнаружит и выполнит эти тесты.

### Нагрузочное тестирование (Locust)

Используется [Locust](https://locust.io/).

**Расположение файлов:**
*   Скрипты Locust: `tests/load/`.
    *   `locustfile_auth.py`: Тестирует **C++ TCP Auth Server** (компонент `auth_server_cpp`) через его внешний TCP/JSON интерфейс на порту `9000`. Этот C++ сервер, в свою очередь, взаимодействует с Python Auth gRPC Service.
    *   `locustfile_game.py`: Заготовка для нагрузочного тестирования **C++ Game Server** (компонент `game_server_cpp`). Требует доработки для реализации конкретных сценариев взаимодействия с его TCP/UDP портами.

**Подготовка к запуску:**
1.  **Запуск окружения:** Для `locustfile_auth.py` и будущих тестов C++ Game Server, убедитесь, что все необходимые сервисы запущены через `docker compose up --build -d` (включая `cpp_auth_tcp_server`, `python_auth_grpc_service`, `cpp_game_server` и их зависимости).
2.  **Python окружение:** Активируйте виртуальное окружение, установите `locust` (`pip install locust`).

**Запуск Locust (пример для `locustfile_auth.py`):**
*   **С веб-интерфейсом:**
    ```bash
    locust -f tests/load/locustfile_auth.py
    ```
    Откройте `http://localhost:8089`. Хост и порт (`localhost:9000`) для `TCPClient` в `locustfile_auth.py` должны соответствовать C++ TCP Auth Server.
*   **Без веб-интерфейса (headless):**
    ```bash
    locust -f tests/load/locustfile_auth.py AuthUser --headless -u 10 -r 2 --run-time 60s
    ```

### Python Интеграционные тесты

Используют `pytest` и `pytest-asyncio`.

**Расположение файлов:**
*   Основной файл: `tests/test_integration.py`. Другие файлы могут быть в `tests/` или `tests/integration/`.

**Что тестируется (примеры):**
*   Взаимодействие между Python компонентами: **Python Auth TCP/JSON Service (`auth_server.main`)** и **Python Game Server (`game_server.main`)**.
*   Корректность работы `AuthClient` (`game_server/auth_client.py`) с Python Auth TCP/JSON сервисом.
*   Взаимодействие Python `game_server` с RabbitMQ (публикация команд).
    *   *Примечание: Эти тесты, как правило, не требуют полного стека Docker Compose с C++ сервисами, если они сфокусированы на взаимодействии Python-компонентов. Для их запуска обычно достаточно запустить Python сервисы локально (например, с помощью `./scripts/run_servers.sh`) и иметь доступные экземпляры брокеров (например, RabbitMQ, запущенный через Docker).*

**Подготовка к запуску:**
1.  **Запуск Python сервисов:** Запустите Python Auth TCP/JSON Service и Python Game Server (например, с помощью `./scripts/run_servers.sh start`). Убедитесь, что RabbitMQ доступен, если тесты его используют.
2.  **Python окружение:** Активируйте виртуальное окружение, установите зависимости (`pip install -r requirements.txt`).

**Запуск тестов:**
Команды выполняются из корневой директории проекта.
```bash
pytest tests/test_integration.py
# или для более подробного вывода
pytest -v tests/test_integration.py
```
Скрипт `scripts/run_tests.sh` также запускает эти тесты.

## Вклад в проект
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

## Будущие улучшения

*   **Реализовать полноценное использование Redis:**
    *   Перенести хранение пользовательских данных из `MOCK_USERS_DB` в `auth_server.user_service.py` на Redis.
    *   Реализовать управление сессиями (создание, валидация, удаление) с использованием Redis, включая TTL для сессий.
    *   Обеспечить консистентность данных между `MOCK_USERS_DB` (если используется для первоначальных пользователей) и Redis.

*   **Реализовать публикацию событий в Kafka из Python-сервисов:**
    *   Добавить публикацию событий аутентификации (например, `user_registered`, `user_loggedin`) из Python Auth gRPC Service и Python Auth TCP/JSON Service в соответствующий топик Kafka.
    *   Реализовать публикацию игровых событий (например, `player_joined`, `tank_destroyed`, `game_ended`) из Python Game Server в Kafka.

*   **Исправить логику регистрации и аутентификации:**
    *   Устранить несоответствие между сохранением хешированного пароля при регистрации (`user_service.create_user`) и ожиданием сырого пароля при аутентификации (`user_service.authenticate_user`). Либо хешировать пароль при аутентификации (потребуется сохранение соли), либо изменить логику хранения.
    *   Реализовать корректный механизм валидации сессионных токенов в Python Auth gRPC Service (вместо повторного использования `AuthenticateUser` с токеном в поле пароля). Добавить отдельный RPC `ValidateSessionToken(ValidateTokenRequest) returns (ValidateTokenResponse)`.

*   **Разработать Python Command Consumer:**
    *   Создать Python-компонент, который бы подписывался на очередь команд `player_commands` в RabbitMQ и обрабатывал их, взаимодействуя с Python Game Server. Это позволит полностью разделить логику обработки команд для C++ и Python реализаций игрового сервера.

*   **Улучшить обработку ошибок и отказоустойчивость:**
    *   Добавить более гранулированную обработку ошибок во всех сервисах.
    *   Внедрить retry-механизмы с экспоненциальной задержкой для всех межсервисных вызовов (gRPC, HTTP, брокеры сообщений).
    *   Реализовать health checks для всех Python-сервисов, чтобы Docker и Kubernetes могли корректно отслеживать их состояние.

*   **Расширить покрытие тестами:**
    *   Добавить больше юнит-тестов для C++ компонентов, особенно для игровой логики.
    *   Разработать интеграционные тесты для C++ стека (например, взаимодействие C++ TCP Auth Server -> Python Auth gRPC Service, C++ Game Server -> Python Auth gRPC Service, C++ Game Server -> Kafka/RabbitMQ).
    *   Дополнить и детализировать сценарии в нагрузочных тестах Locust для C++ Game Server (`locustfile_game.py`).

*   **Документация:**
    *   Дополнить документацию API для всех сервисов (gRPC, TCP/JSON).
    *   Описать детальные сценарии развертывания, включая Kubernetes.
    *   Обновить диаграммы архитектуры и потоков данных по мере внесения изменений.

*   **Безопасность:**
    *   Реализовать использование SSL/TLS для всех внешних и внутренних коммуникаций.
    *   Провести аудит безопасности кода и зависимостей.
    *   Использовать переменные окружения или секреты для всех чувствительных данных (пароли, ключи API).

*   **Конфигурация:**
    *   Активно использовать `core/config.py` для централизованного управления конфигурацией Python-сервисов.
    *   Рассмотреть использование Consul или etcd для динамической конфигурации в распределенной среде.

*   **CI/CD:**
    *   Настроить конвейеры непрерывной интеграции и доставки (CI/CD) для автоматической сборки, тестирования и развертывания сервисов.

*   **Игровая логика (C++ и Python):**
    *   Расширить возможности игровой логики: новые типы танков, бонусы, карты, игровые режимы.
    *   Оптимизировать сетевой код для минимизации задержек.
    *   Улучшить механизмы синхронизации состояния игры.
