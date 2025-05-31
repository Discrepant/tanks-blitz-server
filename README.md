# Серверная архитектура Tanks Blitz (Прототип - Гибрид Python/C++)

Этот проект представляет собой прототип серверной архитектуры для многопользовательской игры Tanks Blitz. Изначально разработанный на Python, проект был частично переписан на C++ для ключевых, производительно-критичных компонентов.
Он включает компоненты для аутентификации (C++ TCP сервер с Python gRPC сервисом), игровой логики (C++), обработки команд и событий через брокеры сообщений (C++ клиенты для Kafka, RabbitMQ), масштабирования, мониторинга и резервного копирования.

## Обзор проекта

Цель проекта - продемонстрировать построение серверной части для MMO-игры с учетом современных практик и технологий. Ключевые аспекты:
- **Гибридный подход:** Python используется для быстрого прототипирования и некоторых сервисов (например, gRPC сервис аутентификации, использующий существующую Python логику), в то время как C++ используется для высокопроизводительных компонентов (игровой сервер, TCP сервер аутентификации, обработчики сообщений).
- Разделение сервисов (аутентификация, игра)
- Асинхронное программирование и обработка событий (Boost.Asio в C++, `asyncio` в Python)
- Брокеры сообщений (Kafka, RabbitMQ) для асинхронных задач и логирования (C++ клиенты)
- Паттерны проектирования (Singleton, Object Pool в C++)
- Контейнеризация (Docker)
- Оркестрация (Kubernetes - концептуально)
- Мониторинг (Prometheus, Grafana)
- Защита от DDoS (Nginx - концептуально)

## Архитектура

Система состоит из следующих основных компонентов:

### 1. Клиент Игры
(Не входит в этот репозиторий)

### 2. Nginx (Входная точка/Балансировщик/Защита от DDoS)
*   **Роль:** Принимает весь входящий трафик.
*   **Проксирование TCP (Auth Server C++):** Nginx прослушивает порт (например, `9000`) и перенаправляет трафик на C++ Сервер Аутентификации.
*   **Проксирование UDP/TCP (Game Server C++):** Nginx прослушивает порты (например, UDP `8889`, TCP `8888`) и перенаправляет трафик на C++ Игровой Сервер.

### 3. Сервер Аутентификации (Auth Server - C++ TCP + Python gRPC)
*   **Роль:** Отвечает за обработку запросов на регистрацию и аутентификацию.
*   **C++ TCP Сервер (`auth_server_app`):**
    *   Прослушивает TCP порт (например, `9000`) для JSON-запросов от клиентов.
    *   Действует как gRPC клиент к Python `AuthService`.
    *   Принимает JSON `{"action": "login/register", "username": "...", "password": "..."}`.
    *   Транслирует эти запросы в gRPC вызовы к Python сервису.
    *   Возвращает ответ от gRPC сервиса клиенту в формате JSON.
*   **Python gRPC Сервис (`auth_grpc_server.py`):**
    *   Прослушивает gRPC порт (например, `localhost:50051`).
    *   Использует существующую Python логику (`user_service.py`) для взаимодействия с Redis (где хранятся учетные данные пользователей).
    *   Отправляет события аудита в Kafka (топик `auth_events`).
*   **Хранение данных:** Учетные данные пользователей хранятся в Redis, управляемом `auth_server/user_service.py`.
*   **Технологии:** C++ (Boost.Asio, gRPC клиент), Python (`grpcio`, `asyncio`, Redis клиент, Kafka клиент).

### 4. Игровой Сервер (Game Server - C++)
*   **Роль:** Обрабатывает основную игровую логику, управляет игровыми сессиями, состоянием игроков (танков) и взаимодействием между ними. Исполняемый файл: `game_server_app`.
*   **Протоколы:** UDP (основные команды) и TCP (управляющие команды, аутентифицированные сессии). Сообщения в JSON.
*   **Управление сессиями (`SessionManager` C++):** Создание, отслеживание, завершение игровых сессий.
*   **Логика обработки игровых команд:**
    1.  Команды от клиентов поступают на `GameUDPHandler` или `GameTCPSession` (C++).
    2.  `GameTCPSession` использует Python gRPC сервис аутентификации для команды `LOGIN`.
    3.  Обработчики публикуют команды (move, shoot) в очередь `player_commands` в RabbitMQ.
    4.  `PlayerCommandConsumer` (C++) извлекает команды из RabbitMQ и делегирует их объектам `Tank` в их `GameSession`.
*   **`TankPool` (C++):** Управляет объектами танков.
*   **События в Kafka (C++):** Отправляет детальные события о ходе игры (движение, урон и т.д.) в Kafka.
*   **Технологии:** C++ (Boost.Asio, librabbitmq-c, librdkafka++).

### 5. Kafka (Брокер сообщений)
*   **Роль:** Сбор, хранение, потоковая обработка событий от C++ и Python компонентов.
*   **Топики:** `player_sessions_history`, `tank_coordinates_history`, `game_events`, `auth_events`.

### 6. RabbitMQ (Брокер сообщений)
*   **Роль:** Асинхронная обработка команд (`player_commands` от C++ обработчиков к C++ консьюмеру).

### 7. Redis
*   **Роль:** Хранение учетных данных пользователей (через Python `user_service.py`). Может использоваться для кэширования и сессий C++ серверами при необходимости.

### 8. Prometheus / Grafana
(Без изменений в их роли, собирают метрики с Python и потенциально C++ сервисов)

## Структура директорий

-   `cpp/`: Корневая директория для всего C++ кода.
    -   `CMakeLists.txt`: Главный CMake-файл для C++ проектов.
    -   `protos/`: Определения `.proto` для gRPC сервисов.
        -   `auth_service.proto`: Определение gRPC сервиса аутентификации.
        -   `CMakeLists.txt`: CMake для генерации кода из `.proto` в библиотеку `auth_grpc_codegen_lib`.
    -   `game_server_cpp/`: Исходный код C++ Игрового Сервера (`game_server_app`).
        -   `CMakeLists.txt`: CMake для сборки игрового сервера и библиотеки `game_logic_lib`.
        -   `*.h`, `*.cpp`: Файлы для UDP/TCP обработчиков, игровых сессий, управления танками, Kafka/RabbitMQ взаимодействия.
    -   `auth_server_cpp/`: Исходный код C++ TCP Сервера Аутентификации (`auth_server_app`).
        -   `CMakeLists.txt`: CMake для сборки сервера аутентификации.
        -   `*.h`, `*.cpp`: Файлы TCP сервера, сессий, gRPC клиента к Python сервису аутентификации.
        -   `grpc_generated/`: (Устарело, генерация теперь централизована в `cpp/protos/`)
    -   `tests/`: Юнит-тесты для C++ компонентов (используя Catch2).
        -   `CMakeLists.txt`: CMake для сборки и запуска тестов.
        -   `main_test.cpp`: Главный файл для запуска тестов Catch2.
        -   `test_*.cpp`: Файлы с тестами.
-   `auth_server/`: Исходный код Python Сервиса Аутентификации.
    -   `auth_grpc_server.py`: Python gRPC сервер, реализующий `AuthService`.
    -   `user_service.py`: Логика взаимодействия с Redis для данных пользователей (используется `auth_grpc_server.py`).
    -   `auth_logic.py`: (Может быть устаревшим, если вся логика в `user_service.py`).
    -   `grpc_generated/`: Сгенерированные Python gRPC файлы из `auth_service.proto`.
-   `game_server/`: (Большая часть логики перенесена в C++) Содержит устаревший Python код игрового сервера. Может использоваться для вспомогательных скриптов или оставшихся Python утилит.
-   `core/`: Общие Python модули.
-   `tests/`: Автоматические тесты для Python компонентов (юнит, интеграционные, нагрузочные).
-   `deployment/`, `monitoring/`, `scripts/`: Без существенных изменений.
-   `requirements.txt`: Список зависимостей Python (включая `grpcio`, `grpcio-tools`).
-   `README.md`: Этот файл.

## Требования

### Python Разработка
-   Python 3.9+
-   См. `requirements.txt` (включает `grpcio`, `grpcio-tools`, `redis`, `kafka-python`, `pika`, `prometheus_client`).

### C++ Разработка
-   C++17 компилятор (GCC, Clang).
-   CMake (версия 3.16+ рекомендуется).
-   Boost библиотеки (System, Asio - версия 1.71+).
-   nlohmann/json (версия 3.x, header-only или системная установка).
-   librabbitmq-c (библиотека и заголовки для разработки).
-   librdkafka++ (библиотека и заголовки для разработки).
-   gRPC (библиотеки C++ и заголовки для разработки, включая gRPC C++ plugin для protoc).
-   Protocol Buffers (библиотека libprotobuf и заголовки, protobuf-compiler).
-   Catch2 (версия 3.x, для юнит-тестов).

### Общие
-   Docker
-   `docker-compose`
-   Git

## Настройка и запуск

### 1. Клонирование и зависимости Python
(Без изменений: клонировать, создать venv, `pip install -r requirements.txt`)

### 2. Зависимости C++
Установите все C++ зависимости, перечисленные выше, используя менеджер пакетов вашей системы (например, `apt-get` для Debian/Ubuntu, `brew` для macOS). Пример для Ubuntu:
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake libboost-system-dev libboost-program-options-dev \
    nlohmann-json3-dev librabbitmq-dev librdkafka-dev \
    libgrpc++-dev libprotobuf-dev protobuf-compiler grpc_cpp_plugin \
    catch2 # (или установить вручную/через CMake FetchContent)
# Для Boost.Asio может потребоваться libboost-dev или установка из исходников для header-only версии.
# Убедитесь, что версии совместимы.
```

### 3. Сборка C++ Компонентов
Из корневой директории проекта:
```bash
cd cpp
mkdir build
cd build
cmake ..
make -j$(nproc)  # или просто 'make'
```
Исполняемые файлы будут находиться в `cpp/build/game_server_cpp/game_server_app` и `cpp/build/auth_server_cpp/auth_server_app`.

### 4. Переменные окружения
(Раздел остается актуальным, но хосты и порты для C++ серверов теперь другие)
-   `AUTH_SERVER_CPP_PORT` (например, `9000`) для C++ Auth TCP Server.
-   `AUTH_GRPC_PYTHON_PORT` (например, `50051`) для Python gRPC Auth Service.
-   `GAME_SERVER_CPP_TCP_PORT` (например, `8888`).
-   `GAME_SERVER_CPP_UDP_PORT` (например, `8889`).

### 5. Запуск

#### Docker Compose (Требует обновления `docker-compose.yml` для C++)
Этот раздел требует значительного обновления для включения сборки C++ образов и их запуска. **Текущий `docker-compose.yml` устарел.**

#### Локальный запуск (для разработки и отладки)
Предполагается, что Kafka, RabbitMQ, Redis запущены (например, через Docker).

1.  **Запустите Python gRPC Auth Service:**
    ```bash
    # Из корневой директории проекта, в активном venv
    export AUTH_GRPC_PYTHON_PORT=50051 # Установите порт, если нужно
    export REDIS_HOST=localhost REDIS_PORT=6379 # и другие для user_service
    python -m auth_server.auth_grpc_server
    ```

2.  **Запустите C++ Auth TCP Server (`auth_server_app`):**
    В новом терминале:
    ```bash
    # Из cpp/build/auth_server_cpp/
    ./auth_server_app <tcp_listen_port> <python_grpc_service_address>
    # Пример:
    ./auth_server_app 9000 localhost:50051
    ```

3.  **Запустите C++ Game Server (`game_server_app`):**
    В новом терминале:
    ```bash
    # Из cpp/build/game_server_cpp/
    # main.cpp для game_server_app должен быть обновлен для приема конфигурации
    # (порты, адреса RabbitMQ/Kafka, адрес Auth gRPC сервиса) через переменные окружения или аргументы командной строки.
    # Пример (концептуальный, main.cpp нужно доработать для такой конфигурации):
    export GAME_TCP_PORT=8888 GAME_UDP_PORT=8889 \
           RABBITMQ_HOST=localhost KAFKA_BOOTSTRAP_SERVERS=localhost:29092 \
           AUTH_GRPC_SERVICE_ADDRESS=localhost:50051
    ./game_server_app
    ```
    *Порядок запуска важен: брокеры -> Python gRPC Auth Service -> C++ Auth TCP Server -> C++ Game Server.*

## Тестирование

### Python Тесты
(Раздел остается актуальным для существующих Python тестов)

### C++ Юнит Тесты
Юнит-тесты для C++ компонентов используют Catch2.

1.  **Сборка тестов:**
    Тесты собираются вместе с C++ компонентами при выполнении `cmake .. && make` в директории `cpp/build/`.
    Исполняемый файл тестов: `cpp/build/tests/game_tests`.

2.  **Запуск C++ тестов:**
    Из директории `cpp/build/`:
    ```bash
    ctest -V  # -V для подробного вывода
    ```
    Или запустить исполняемый файл напрямую:
    ```bash
    ./tests/game_tests [catch2_options]
    ```
    **Важно:** Некоторые C++ тесты (например, `test_auth_tcp_session.cpp`, `test_game_tcp_session.cpp` для логина) могут требовать запущенного Python gRPC Auth Service (`auth_server.auth_grpc_server`) на `localhost:50051`.

## Удаление или Обновление Устаревшей Информации
-   Инструкции по запуску Python серверов (`auth_server/main.py`, `game_server/main.py`) как основных игровых сервисов теперь устарели. `auth_server/main.py` заменен на `auth_grpc_server.py` в связке с C++ TCP сервером. `game_server/main.py` полностью заменен C++ реализацией.
-   Старая архитектура, описывающая полностью Python-based серверы, должна быть обновлена.

## Участие в разработке (Contributing)
(Раздел остается актуальным)

## Логирование
(Раздел остается актуальным, но теперь относится и к C++ логам, и к Python)

## Дальнейшие улучшения и TODO
-   **Обновить `docker-compose.yml`** для сборки и запуска C++ сервисов вместе с Python gRPC сервисом и остальной инфраструктурой.
-   Создать Dockerfile для C++ приложений.
-   Реализовать передачу конфигурации в C++ приложения через переменные окружения или файлы конфигурации (вместо жестко закодированных значений или простых аргументов `main`).
-   Расширить C++ юнит-тесты, особенно для проверки взаимодействия с внешними сервисами с использованием моков (gRPC, RabbitMQ, Kafka).
-   Интегрировать C++ сервисы с Prometheus для сбора метрик.
