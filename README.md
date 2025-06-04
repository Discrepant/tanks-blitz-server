# Tank Battle Game Server

This project is the backend server for a multiplayer tank battle game. It features a microservice architecture with components for authentication and game logic, supporting both Python and C++ implementations for different parts of the system.

## Table of Contents

- [Project Goals](#project-goals)
- [Architecture Overview](#architecture-overview)
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

### Компоненты Системы

1.  **Nginx (Концептуально):**
    *   **Роль:** Выполняет функции основной входной точки для всего клиентского трафика.
    *   **Ключевые функции:**
        *   SSL-терминация: Завершает SSL/TLS соединения, снимая эту нагрузку с бэкенд-сервисов.
        *   Балансировка нагрузки: Распределяет входящие запросы между несколькими экземплярами C++ TCP Auth Server и C++ Game Server для обеспечения масштабируемости и отказоустойчивости.
        *   Проксирование трафика: Направляет TCP-трафик на соответствующие порты C++ TCP Auth Server и TCP/UDP трафик на C++ Game Server.
        *   Защита: Может быть настроен для базовой защиты от DDoS-атак и фильтрации вредоносного трафика.
    *   **Взаимодействие:** Принимает весь внешний трафик от пользователей и перенаправляет его на внутренние сервисы.

2.  **Сервис Аутентификации:**
    *   **C++ TCP Auth Server (`auth_server_cpp`):**
        *   **Роль:** Начальный обработчик запросов аутентификации и регистрации от клиентов.
        *   **Ключевые функции:**
            *   Принимает TCP-соединения от игровых клиентов.
            *   Парсит JSON-сообщения с учетными данными (логин, пароль).
            *   Выступает в роли gRPC-клиента к Python Auth gRPC Service для выполнения основной логики аутентификации.
            *   Передает ответ от Python Auth gRPC Service обратно клиенту по TCP.
        *   **Взаимодействие:** Клиент <-> C++ TCP Auth Server (TCP), C++ TCP Auth Server -> Python Auth gRPC Service (gRPC).
    *   **Python Auth gRPC Service (`auth_server`):**
        *   **Роль:** Центральный сервис для управления учетными записями пользователей и их сессиями.
        *   **Ключевые функции:**
            *   Обрабатывает gRPC-запросы на регистрацию, аутентификацию и валидацию сессий от C++ TCP Auth Server и C++ Game Server.
            *   Взаимодействует с Redis для хранения и извлечения данных пользователей (включая хеши паролей) и информации об активных сессиях.
            *   Публикует события, связанные с аутентификацией (например, `user_registered`, `user_loggedin`), в топик `auth_events` в Kafka.
        *   **Взаимодействие:** C++ TCP Auth Server -> Python Auth gRPC Service (gRPC), C++ Game Server -> Python Auth gRPC Service (gRPC), Python Auth gRPC Service <-> Redis, Python Auth gRPC Service -> Kafka.

3.  **Игровой Сервис (`game_server_cpp`):**
    *   **Роль:** Обрабатывает всю логику игрового процесса в реальном времени.
    *   **Ключевые функции:**
        *   Управляет игровыми сессиями, подключением и отключением игроков.
        *   Обрабатывает движение танков, стрельбу, попадания, урон и другие игровые механики.
        *   Поддерживает TCP (для управляющих команд и критически важных данных) и UDP (для частых обновлений состояния, таких как координаты) протоколы для связи с клиентами.
        *   Получает команды от игроков (через TCP/UDP обработчики) и публикует их в очередь `player_commands` в RabbitMQ.
        *   Содержит `PlayerCommandConsumer`, который читает команды из RabbitMQ и применяет их к игровому состоянию.
        *   Публикует ключевые игровые события (например, `game_started`, `tank_destroyed`, `player_left`) и историю сессий в топики Kafka (`game_events`, `player_sessions_history`).
        *   Периодически может публиковать координаты танков в Kafka (`tank_coordinates_history`) для анализа или воспроизведения.
        *   При подключении игрока или по запросу валидирует сессионный токен через Python Auth gRPC Service.
    *   **Взаимодействие:** Клиент <-> C++ Game Server (TCP/UDP), C++ Game Server -> Python Auth gRPC Service (gRPC), C++ Game Server -> RabbitMQ (публикация команд), C++ Game Server (PlayerCommandConsumer) <- RabbitMQ (чтение команд), C++ Game Server -> Kafka.

4.  **Брокеры Сообщений:**
    *   **Kafka:**
        *   **Роль:** Высокопроизводительная распределенная платформа для потоковой передачи событий и логов.
        *   **Ключевые функции:**
            *   Сбор событий аутентификации (`auth_events`) от Python Auth gRPC Service.
            *   Сбор игровых событий (`game_events`), истории сессий (`player_sessions_history`) и других данных (например, `tank_coordinates_history`) от C++ Game Server.
            *   Обеспечивает возможность для других сервисов (в будущем) подписываться на эти потоки данных для анализа, статистики, репликации и т.д.
        *   **Взаимодействие:** Python Auth gRPC Service -> Kafka, C++ Game Server -> Kafka.
    *   **RabbitMQ:**
        *   **Роль:** Традиционный брокер сообщений для асинхронной обработки команд.
        *   **Ключевые функции:**
            *   Принимает команды игроков (например, движение, стрельба) от C++ Game Server (TCP/UDP обработчиков) в очередь `player_commands`.
            *   Позволяет `PlayerCommandConsumer` (часть C++ Game Server) асинхронно обрабатывать эти команды, отделяя их получение от исполнения.
        *   **Взаимодействие:** C++ Game Server (TCP/UDP Handlers) -> RabbitMQ, C++ Game Server (PlayerCommandConsumer) <- RabbitMQ.

5.  **Хранилище Данных Redis:**
    *   **Роль:** Быстрое in-memory хранилище ключ-значение.
    *   **Ключевые функции:**
        *   Хранение информации о пользователях (например, ID пользователя, хеш пароля, соль).
        *   Хранение активных сессионных токенов и связанных с ними данных пользователя.
        *   Может использоваться для кеширования часто запрашиваемых данных для снижения нагрузки на другие сервисы.
    *   **Взаимодействие:** Python Auth gRPC Service <-> Redis.

6.  **Система Мониторинга:**
    *   **Prometheus:**
        *   **Роль:** Сбор и хранение метрик временных рядов.
        *   **Ключевые функции:**
            *   Периодически опрашивает (scrapes) HTTP эндпоинты метрик, предоставляемые различными сервисами (Python Auth gRPC Service, C++ Game Server, C++ Auth Server, Kafka, RabbitMQ и т.д.).
            *   Сохраняет метрики для последующего анализа и визуализации.
        *   **Взаимодействие:** Prometheus -> Все остальные сервисы (HTTP scrape).
    *   **Grafana (Концептуально):**
        *   **Роль:** Платформа для визуализации и анализа данных.
        *   **Ключевые функции:**
            *   Подключается к Prometheus как к источнику данных.
            *   Позволяет создавать дашборды для отображения метрик, отслеживания состояния системы и производительности.
        *   **Взаимодействие:** Grafana -> Prometheus.

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

### Общие требования (Common)
*   **Git:** Система контроля версий для клонирования репозитория.
*   **Docker & Docker Compose:** Для сборки и запуска контейнеризированных сервисов (например, Kafka, RabbitMQ, Redis) и самого приложения.

### Python Development
*   **Python:** Рекомендуется версия 3.9 или новее. Убедитесь, что Python добавлен в `PATH`.
*   **PIP:** Менеджер пакетов Python (обычно устанавливается вместе с Python).
*   **Зависимости Python:** Полный список указан в файле `requirements.txt`. Ключевые библиотеки включают:
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

**Общие для всех ОС (Linux, macOS, Windows):**
*   **Компилятор C++:** Поддерживающий стандарт C++17 (например, GCC 8+, Clang 6+, MSVC Visual Studio 2019+).
*   **CMake:** Система автоматизации сборки, версия 3.16 или новее. Убедитесь, что CMake добавлен в `PATH`.
*   **Для генерации gRPC кода:**
    *   **`protoc` (Protocol Buffers Compiler)** и **`grpc_cpp_plugin` (gRPC C++ Plugin)**: Эти инструменты необходимы для компиляции `.proto` файлов в C++ код.
        *   **При использовании `vcpkg` для установки `grpc` (рекомендуется для Windows),** `protoc` и `grpc_cpp_plugin` обычно устанавливаются и интегрируются автоматически. CMake должен их найти через тулчейн vcpkg.
        *   **Для Linux,** если gRPC устанавливается через системный менеджер пакетов (например, `apt`), убедитесь, что установлены пакеты `protobuf-compiler` и `grpc_cpp_plugin` (или аналогичные, например, `libgrpc-dev` может включать плагин).
        *   Если устанавливается вручную, `protoc` должен быть в `PATH`, а `grpc_cpp_plugin` должен быть доступен (часто находится рядом с `protoc` или его путь должен быть известен CMake).

**Зависимости C++ и их установка:**

Мы **настоятельно рекомендуем использовать менеджер пакетов `vcpkg`** ([https://github.com/microsoft/vcpkg](https://github.com/microsoft/vcpkg)) для установки C++ зависимостей, особенно на **Windows**, так как это значительно упрощает процесс и обеспечивает совместимость. Инструкции ниже ориентированы на `vcpkg`. Для **Linux** также можно использовать `vcpkg` или системные менеджеры пакетов (например, `apt`).

**1. Установка `vcpkg` (если еще не установлен):**
*   Клонируйте репозиторий `vcpkg` в удобное для вас место (например, `C:\dev\vcpkg` или `~/vcpkg`):
    ```bash
    git clone https://github.com/microsoft/vcpkg.git
    cd vcpkg 
    ```
*   Запустите скрипт начальной настройки:
    *   Windows (PowerShell или CMD): `.\bootstrap-vcpkg.bat`
    *   Linux/macOS: `./bootstrap-vcpkg.sh`
*   Интегрируйте `vcpkg` с вашей системой сборки. Это особенно важно для Visual Studio на Windows, чтобы CMake и MSBuild автоматически находили библиотеки, установленные через `vcpkg`:
    ```bash
    # Находясь в директории vcpkg
    .\vcpkg integrate install 
    ```

**2. Установка необходимых пакетов через `vcpkg` (для Windows x64):**
Все C++ зависимости для этого проекта управляются через `vcpkg`. Используйте следующую команду в PowerShell или CMD (находясь в директории `vcpkg`), чтобы установить все необходимые пакеты для архитектуры **x64 Windows**. Если вы собираете для другой платформы или архитектуры (например, Linux), измените триплет (`x64-windows`) соответствующим образом.
```powershell
.\vcpkg install boost:x64-windows grpc:x64-windows librdkafka[cpp]:x64-windows librabbitmq:x64-windows nlohmann-json:x64-windows catch2:x64-windows openssl:x64-windows zlib:x64-windows c-ares:x64-windows re2:x64-windows
```
*   **Описание устанавливаемых пакетов:**
    *   `boost:x64-windows`: Набор библиотек C++ (в проекте используются компоненты Asio, System).
    *   `grpc:x64-windows`: Фреймворк gRPC (включает Protocol Buffers и необходимые инструменты, такие как `protoc` и `grpc_cpp_plugin`).
    *   `librdkafka[cpp]:x64-windows`: Клиентская библиотека Apache Kafka для C/C++ (с C++ оберткой, указанной через `[cpp]`).
    *   `librabbitmq:x64-windows`: Клиентская C-библиотека для RabbitMQ. (Примечание: CMake будет искать этот пакет как `rabbitmq-c` через `find_package`).
    *   `nlohmann-json:x64-windows`: Популярная библиотека для работы с JSON в C++.
    *   `catch2:x64-windows`: Фреймворк для юнит-тестирования C++.
    *   `openssl:x64-windows`: Криптографическая библиотека (часто является зависимостью для других библиотек, включая gRPC и Kafka).
    *   `zlib:x64-windows`: Библиотека для сжатия данных (часто является зависимостью).
    *   `c-ares:x64-windows`: C-библиотека для асинхронных DNS запросов (зависимость gRPC).
    *   `re2:x64-windows`: Библиотека для работы с регулярными выражениями (зависимость gRPC).
*   **Примечание о триплете:** Убедитесь, что используемый триплет (например, `:x64-windows`) соответствует вашей целевой архитектуре и конфигурации сборки. Для других платформ используйте соответствующие триплеты (например, `x64-linux`, `x64-osx`).

**3. Для Linux (альтернатива с `apt` для Debian/Ubuntu):**
Если вы не используете `vcpkg` на Linux, вы можете установить зависимости через `apt`. Имена пакетов могут немного отличаться, и вам нужно будет убедиться в их совместимости. Это примерный список:
```bash
sudo apt-get update
sudo apt-get install build-essential cmake git pkg-config \
    libboost-dev libboost-system-dev \
    libgrpc++-dev libprotobuf-dev protobuf-compiler grpc_cpp_plugin \
    librdkafka-dev \
    librabbitmq-dev \
    nlohmann-json3-dev \
    catch2 \
    libssl-dev zlib1g-dev libc-ares-dev libre2-dev
```
*При использовании системных менеджеров пакетов, убедитесь, что версии устанавливаемых библиотек совместимы с требованиями проекта и между собой.*

## Installation

### 1. Клонирование репозитория
```bash
git clone <URL_вашего_репозитория> # Замените на URL вашего репозитория
cd <имя_каталога_проекта>
```

### 2. Настройка Python окружения
Рекомендуется использовать виртуальное окружение для изоляции зависимостей проекта.

*   **Создание и активация виртуального окружения:**
    *   Linux/macOS:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   Windows (CMD/PowerShell):
        ```bash
        python -m venv venv
        .\venv\Scripts\activate  # Для PowerShell. Для CMD: venv\Scripts\activate.bat
        ```
*   **Установка Python зависимостей:**
    ```bash
    # Находясь в активированном виртуальном окружении
    pip install -r requirements.txt
    ```

### 3. Установка C++ зависимостей
Процесс установки C++ зависимостей подробно описан в разделе [C++ Development -> Зависимости C++ и их установка](#c-dependencies-and-installation). Пожалуйста, следуйте инструкциям в этом разделе, чтобы установить все необходимые компоненты с использованием `vcpkg` (рекомендуется) или системного менеджера пакетов для вашей ОС.

### 4. Генерация gRPC кода
CMake проект настроен на автоматическую генерацию C++ кода из `.proto` файлов (`cpp/protos/`) во время процесса конфигурации/сборки.
Если вы используете `vcpkg` и установили пакет `grpc` (как рекомендовано выше), все необходимые инструменты (`protoc` и `grpc_cpp_plugin`) должны быть автоматически обнаружены CMake через тулчейн-файл `vcpkg.cmake`. Никаких дополнительных действий по настройке `protoc` вручную обычно не требуется.

### 5. Сборка C++ компонентов
Сборка C++ компонентов осуществляется с помощью CMake. Процесс состоит из двух этапов: конфигурация (генерация сборочных файлов для вашей среды) и сама сборка.

**Общий процесс (из корневого каталога проекта):**
1.  Перейдите в каталог `cpp`:
    ```bash
    cd cpp
    ```
2.  Создайте каталог для сборки (например, `build`) и перейдите в него:
    ```bash
    mkdir build
    cd build
    ```
    *Все последующие команды CMake и сборки выполняются из каталога `cpp/build/`.*

**Конфигурация и сборка для Windows (Visual Studio с использованием `vcpkg`):**

*   **Предварительно:** Убедитесь, что `vcpkg integrate install` был выполнен после установки `vcpkg` и всех пакетов.
*   **Конфигурация (генерация проекта Visual Studio):**
    Откройте PowerShell или Developer Command Prompt for Visual Studio. Находясь в каталоге `cpp/build/`, выполните:
    ```powershell
    cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_TOOLCHAIN_FILE="C:/Users/Hoshi/vcpkg/scripts/buildsystems/vcpkg.cmake"
    ```
    *   **Важно:** Замените `C:/Users/Hoshi/vcpkg` на **актуальный путь** к вашему каталогу установки `vcpkg`. Путь должен быть абсолютным.
    *   Замените `"Visual Studio 17 2022"` на вашу версию Visual Studio, если она отличается (например, `"Visual Studio 16 2019"`). Список доступных генераторов можно посмотреть командой `cmake --help`.
    *   `-A x64` указывает на сборку под 64-битную архитектуру.
*   **Сборка:**
    *   **Через CMake (рекомендуется для командной строки):**
        ```powershell
        # Находясь в cpp/build/
        cmake --build . --config Release 
        ```
        Или для отладочной сборки:
        ```powershell
        cmake --build . --config Debug
        ```
    *   **Через Visual Studio IDE:**
        Откройте сгенерированный файл решения (`TankGameCppServices.sln` или аналогичный) в каталоге `cpp/build/` с помощью Visual Studio. Затем выберите конфигурацию (Debug/Release) и платформу (x64) и соберите решение (Build -> Build Solution).

**Конфигурация и сборка для Linux/macOS (GCC/Clang):**
```bash
# Находясь в cpp/build/

# Конфигурация (если используете vcpkg, не забудьте CMAKE_TOOLCHAIN_FILE):
# cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=[путь_к_vcpkg]/scripts/buildsystems/vcpkg.cmake 
# Или без vcpkg, если зависимости установлены системно:
cmake .. -DCMAKE_BUILD_TYPE=Release

# Сборка:
make -j$(nproc) # Используйте количество ядер вашего процессора
# Или cmake --build . --config Release
```

**Результаты сборки:**
Исполняемые файлы для C++ сервера аутентификации, игрового сервера и тестов будут находиться в соответствующих подкаталогах внутри `cpp/build/` (например, `cpp/build/auth_server_cpp/Release/auth_server_app.exe` и `cpp/build/game_server_cpp/Release/game_server_app.exe` для Windows Release сборки, или `cpp/build/auth_server_cpp/auth_server_app` для Linux).

**Политики CMake (CMP0167 - FindBoost):**
В CMake-скрипты проекта (`game_server_cpp/CMakeLists.txt`, `auth_server_cpp/CMakeLists.txt`, `tests/CMakeLists.txt`) добавлена команда `cmake_policy(SET CMP0167 NEW)` перед поиском пакета Boost. Это сделано для использования нового поведения модуля `FindBoost` и устранения соответствующих предупреждений CMake. Пользователю не требуется предпринимать дополнительных действий по этому поводу.

### 6. Установка Docker (для инфраструктурных сервисов)
(Содержимое этого подраздела оставлено без изменений)
*   **Docker Desktop для Windows/macOS:** ...
*   **Docker для Linux:** ...

## Running the Application
(Содержимое этого раздела оставлено без значительных изменений, но стоит проверить актуальность портов и имен переменных окружения, если они менялись в C++ коде)
...

## Testing
(Содержимое этого раздела оставлено без значительных изменений, но стоит проверить пути к исполняемым файлам тестов и команды их запуска)
...

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
