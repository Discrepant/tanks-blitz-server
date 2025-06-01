# Tank Battle Game Server

This project is the backend server for a multiplayer tank battle game. It features a microservice architecture with components for authentication and game logic, supporting both Python and C++ implementations for different parts of the system.

## Table of Contents

- [Project Goals](#project-goals)
- [Architecture Overview](#architecture-overview)
- [Directory Structure](#directory-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Contributing](#contributing)
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

## Architecture Overview

Система спроектирована как набор взаимодействующих микросервисов, обеспечивающих различные аспекты игры и аутентификации.

1.  **Nginx (Концептуально):**
    *   **Роль:** Выполняет функции входной точки для всего трафика, обеспечивает SSL-терминацию, балансировку нагрузки между экземплярами сервисов и, потенциально, защиту от DDoS-атак.
    *   **Проксирование:** Направляет TCP-трафик на C++ TCP сервер аутентификации и TCP/UDP трафик на C++ игровой сервер. Конкретные порты и правила маршрутизации настраиваются в конфигурации Nginx.

2.  **Сервис Аутентификации:** Состоит из двух основных компонентов:
    *   **C++ TCP Auth Server (`auth_server_cpp`):**
        *   **Назначение:** Принимает первичные TCP-соединения от игровых клиентов для запросов на вход (логин) или регистрацию.
        *   **Взаимодействие:** Получает от клиента JSON-сообщения, парсит их и далее выступает в роли gRPC-клиента к Python Auth gRPC сервису для выполнения фактической логики аутентификации. Ответ от gRPC сервиса транслируется обратно клиенту через TCP.
        *   **Протокол:** TCP для связи с клиентом, gRPC для связи с Python Auth gRPC сервисом.
    *   **Python Auth gRPC Service (`auth_server`):**
        *   **Назначение:** Реализует основную логику аутентификации и управления пользователями. Обрабатывает gRPC-запросы от C++ TCP Auth Server.
        *   **Взаимодействие с Redis:** Через модуль `user_service.py` взаимодействует с Redis для создания, проверки и хранения учетных данных пользователей, а также управления сессиями.
        *   **Публикация событий:** Публикует события аутентификации (например, успешный вход, новая регистрация) в топик Kafka (`auth_events`) для последующего анализа или обработки другими сервисами.
        *   **Протокол:** gRPC.

3.  **Игровой Сервис (`game_server_cpp`):**
    *   **Реализация:** Полностью на C++ для обеспечения высокой производительности и низких задержек, критичных для игрового процесса в реальном времени.
    *   **Основные функции:** Управляет игровой логикой, сессиями игроков, движением танков, механикой боя, подсчетом очков и т.д.
    *   **Сетевое взаимодействие:**
        *   **TCP:** Используется для надежной передачи управляющих сообщений. Например, при входе игрока в игровой мир (после успешной аутентификации), создается TCP-сессия. Эта сессия может также инициировать вызовы к сервису аутентификации (через его gRPC интерфейс) для проверки токена сессии.
        *   **UDP:** Применяется для частых обновлений состояния игры, таких как координаты танков, информация о выстрелах и других действиях, где допустима потеря пакетов ради скорости доставки.
    *   **Обработка команд игрока:**
        *   Команды от игроков (например, "двигаться вперед", "стрелять") могут поступать через TCP или UDP обработчики.
        *   Эти команды далее публикуются в очередь RabbitMQ (`player_commands`).
        *   Специальный компонент `PlayerCommandConsumer` (также на C++) считывает команды из RabbitMQ и применяет их к соответствующим игровым сессиям и объектам (танкам). Это позволяет отделить получение команд от их обработки.
    *   **Публикация игровых событий:** Важные игровые события (например, начало/конец матча, изменение счета, уничтожение танка) публикуются в соответствующий топик Kafka (`game_events`, `player_sessions_history`) для сбора статистики, логирования или других целей.

4.  **Очереди Сообщений:**
    *   **Kafka (`core/message_broker_clients.py` для Python, `librdkafka` для C++):**
        *   **Назначение:** Используется как распределенная потоковая платформа для агрегации логов, сбора метрик и потоковой передачи событий из различных сервисов.
        *   **Топики (примеры):** `auth_events`, `game_events`, `player_sessions_history` (история игровых сессий), `tank_coordinates_history` (для записи траекторий движения).
    *   **RabbitMQ (`pika` для Python, `librabbitmq-c` для C++):**
        *   **Назначение:** Применяется для асинхронной обработки задач и более традиционных сценариев обмена сообщениями между сервисами, где требуется гарантированная доставка и гибкая маршрутизация.
        *   **Очереди (примеры):** `player_commands` (для команд игроков, отправляемых в игровой сервер).

5.  **Хранилище Данных Redis (`core/redis_client.py`):**
    *   **Назначение:** Используется Python Auth gRPC сервисом для хранения и быстрого доступа к данным пользователей (например, хеши паролей, информация о профиле) и активных сессий. Может также применяться для кеширования часто запрашиваемых данных.

6.  **Мониторинг (`monitoring/`):**
    *   **Prometheus:** Настроен для сбора (scraping) метрик с различных компонентов приложения. В Python-сервисах это обычно делается с использованием библиотеки `prometheus_client`. Для C++ сервисов может потребоваться дополнительная интеграция (например, через специальную библиотеку или http-endpoint, предоставляющий метрики в формате Prometheus).
    *   **Цель:** Обеспечение наблюдаемости системы, отслеживание ее производительности и оперативное выявление проблем.

**Потоки данных (примеры):**

*   **Регистрация пользователя:**
    1.  Клиент -> C++ TCP Auth Server (JSON запрос на регистрацию).
    2.  C++ TCP Auth Server -> Python Auth gRPC Service (gRPC запрос на регистрацию).
    3.  Python Auth gRPC Service -> Redis (сохранение данных нового пользователя).
    4.  Python Auth gRPC Service -> Kafka (событие "новый пользователь зарегистрирован" в `auth_events`).
    5.  Python Auth gRPC Service -> C++ TCP Auth Server (gRPC ответ).
    6.  C++ TCP Auth Server -> Клиент (JSON ответ).

*   **Вход пользователя и начало игры:**
    1.  Клиент -> C++ TCP Auth Server (JSON запрос на логин).
    2.  C++ TCP Auth Server -> Python Auth gRPC Service (gRPC запрос на логин).
    3.  Python Auth gRPC Service -> Redis (проверка учетных данных, создание/обновление сессии, генерация токена).
    4.  Python Auth gRPC Service -> Kafka (событие "пользователь вошел" в `auth_events`).
    5.  Python Auth gRPC Service -> C++ TCP Auth Server (gRPC ответ с токеном сессии).
    6.  C++ TCP Auth Server -> Клиент (JSON ответ с токеном сессии).
    7.  Клиент -> C++ Game Server (TCP соединение с токеном сессии для входа в игру).
    8.  C++ Game Server (TCP Session) -> Python Auth gRPC Service (gRPC запрос для валидации токена сессии).
    9.  Python Auth gRPC Service -> Redis (проверка токена).
    10. Python Auth gRPC Service -> C++ Game Server (TCP Session) (gRPC ответ).
    11. C++ Game Server: если токен валиден, игрок входит в игру, создается объект танка из пула.

*   **Отправка команды игроком (например, движение):**
    1.  Клиент -> C++ Game Server (UDP или TCP сообщение с командой).
    2.  C++ Game Server (UDP/TCP Handler) -> RabbitMQ (публикация команды в очередь `player_commands`).
    3.  C++ Game Server (PlayerCommandConsumer) -> Считывает команду из RabbitMQ.
    4.  C++ Game Server (PlayerCommandConsumer) -> Обновляет состояние игровой сессии и танка игрока.
    5.  C++ Game Server -> Рассылает обновления состояния игры другим клиентам (обычно по UDP).
    6.  C++ Game Server -> Kafka (публикация события, например, новые координаты танка в `tank_coordinates_history`).

## Directory Structure

Ниже представлена структура основных каталогов и файлов проекта:

*   `auth_server/`: Исходный код Python gRPC сервиса аутентификации.
    *   `main.py`: Точка входа для запуска Python TCP сервера аутентификации (устаревшая версия, основной функционал в `auth_grpc_server.py`).
    *   `auth_grpc_server.py`: Основная логика gRPC сервера аутентификации.
    *   `user_service.py`: Модуль для взаимодействия с Redis (хранение и управление данными пользователей).
    *   `tcp_handler.py`: Обработчик TCP соединений для Python сервера аутентификации (устаревшая версия).
    *   `grpc_generated/`: Сгенерированные Python классы из `.proto` файлов для gRPC.
    *   `metrics.py`: Настройка и экспорт метрик Prometheus для сервиса аутентификации.
*   `auth_server_cpp/`: Исходный код C++ TCP сервера аутентификации.
    *   `main_auth.cpp`: Точка входа для C++ сервера аутентификации.
    *   `auth_tcp_server.h/cpp`: Логика TCP сервера.
    *   `auth_tcp_session.h/cpp`: Логика обработки клиентской сессии TCP.
    *   `grpc_generated/`: Сгенерированные C++ классы из `.proto` файлов для gRPC клиента.
    *   `CMakeLists.txt`: Файл для сборки C++ сервера аутентификации с помощью CMake.
*   `core/`: Общие Python модули, используемые различными сервисами.
    *   `redis_client.py`: Клиент для взаимодействия с Redis.
    *   `message_broker_clients.py`: Клиенты для работы с Kafka и RabbitMQ.
*   `cpp/`: Корневой каталог для всего C++ кода.
    *   `auth_server_cpp/`: Исходный код C++ TCP сервера аутентификации (дублирует информацию из верхнеуровневого `auth_server_cpp/` для ясности структуры C++ части).
    *   `game_server_cpp/`: Исходный код C++ игрового сервера.
    *   `protos/`: Каталог с `.proto` файлами, определяющими контракты gRPC сервисов.
        *   `auth_service.proto`: Определение gRPC сервиса аутентификации.
    *   `tests/`: Каталог с C++ юнит-тестами.
    *   `CMakeLists.txt`: Главный CMake-файл для сборки всех C++ компонентов проекта.
*   `deployment/`: Скрипты и конфигурационные файлы для развертывания.
    *   `docker-compose.yml`: Файл для оркестрации Docker-контейнеров локально.
    *   `kubernetes/`: Манифесты Kubernetes для развертывания в кластере.
    *   `nginx/`: Конфигурационные файлы для Nginx.
    *   `redis_backup/`: Скрипты для резервного копирования данных Redis.
    *   `entrypoint.sh`: Точка входа для Docker контейнеров.
*   `game_server/`: Устаревший Python код игрового сервера. Основная игровая логика перенесена в `game_server_cpp/`.
    *   `main.py`: Точка входа для Python игрового сервера.
    *   `udp_handler.py`, `tcp_handler.py`: Обработчики UDP и TCP соединений.
    *   Остальные файлы содержат логику игры, управление сессиями и т.д.
*   `game_server_cpp/`: Исходный код C++ игрового сервера.
    *   `main.cpp`: Точка входа для C++ игрового сервера.
    *   `tcp_handler.h/cpp`, `tcp_session.h/cpp`: Логика TCP сервера и обработки сессий.
    *   `udp_handler.h/cpp`: Логика UDP сервера.
    *   `game_session.h/cpp`: Управление игровой сессией.
    *   `session_manager.h/cpp`: Управление всеми активными сессиями.
    *   `tank.h/cpp`, `tank_pool.h/cpp`: Логика игровых объектов (танков) и их пула.
    *   `command_consumer.h/cpp`: Потребитель команд из RabbitMQ.
    *   `kafka_producer_handler.h/cpp`: Обработчик для отправки сообщений в Kafka.
    *   `CMakeLists.txt`: Файл для сборки C++ игрового сервера.
*   `monitoring/`: Конфигурации для системы мониторинга.
    *   `prometheus/prometheus.yml`: Конфигурационный файл Prometheus.
*   `protos/`: Общие `.proto` файлы. (Часто это символическая ссылка или копия `cpp/protos/`).
*   `tests/`: Автоматизированные тесты на Python.
    *   `unit/`: Юнит-тесты для отдельных модулей Python.
    *   `load/`: Тесты нагрузки с использованием Locust (`locustfile_auth.py`, `locustfile_game.py`).
    *   `test_integration.py`: Интеграционные тесты для Python компонентов.
    *   `test_auth_server.py`, `test_game_server.py`: Специфичные тесты для серверов.
*   `.gitignore`: Определяет намеренно неотслеживаемые файлы, которые Git должен игнорировать.
*   `Dockerfile`: Инструкции для сборки Docker-образа основного Python приложения.
*   `auth_server/Dockerfile`: Dockerfile для Python gRPC сервиса аутентификации.
*   `cpp/Dockerfile`: Dockerfile для сборки C++ компонентов.
*   `requirements.txt`: Список зависимостей Python.
*   `pyproject.toml`: Файл конфигурации проекта Python (например, для `pytest` или сборщиков).
*   `run_servers.sh`: Скрипт для запуска (устаревших) Python серверов.
*   `run_tests.sh`: Скрипт для запуска Python тестов.
*   `check_udp_bind.py`, `send_tcp_test.py`, `test_script.sh`: Вспомогательные скрипты для тестирования и проверки.

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
*   **Protocol Buffers Compiler (`protoc`):** Компилятор для `.proto` файлов. Версия должна быть совместима с используемой библиотекой `libprotobuf` (например, v3.x, рекомендуется последняя стабильная версия из серии 3.x или соответствующая используемым gRPC библиотекам, например, protobuf 5.29.x для grpc 1.71.x). `protoc` должен быть в `PATH`.
*   **gRPC `grpc_cpp_plugin`:** Плагин для `protoc` для генерации C++ кода gRPC. Обычно поставляется вместе с gRPC.

**Зависимости C++ и их установка:**

Мы рекомендуем использовать менеджер пакетов `vcpkg` для установки C++ зависимостей на **Windows**, так как это значительно упрощает процесс. Для **Linux** можно использовать системные менеджеры пакетов (apt, yum и т.д.) или `vcpkg`.

1.  **Boost (>= 1.71.0, рекомендуется последняя стабильная):**
    *   Используемые компоненты: `asio` (для сетевого взаимодействия), `system` (для `asio`), `program_options` (для парсинга аргументов командной строки, если используется).
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install boost-asio boost-system boost-program-options
        ```
    *   **Linux (apt):**
        ```bash
        sudo apt-get install libboost-asio-dev libboost-system-dev libboost-program-options-dev
        ```

2.  **gRPC (>= 1.4x, рекомендуется последняя стабильная, например, 1.71.x):**
    *   Включает Protocol Buffers как зависимость.
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install grpc
        ```
        *Примечание: vcpkg автоматически установит совместимую версию Protocol Buffers и другие зависимости gRPC.*
    *   **Linux (apt):**
        ```bash
        sudo apt-get install libgrpc++-dev libprotobuf-dev protobuf-compiler grpc_cpp_plugin
        ```
        *Убедитесь, что версии `libgrpc++-dev` и `protobuf-compiler` (и `grpc_cpp_plugin`) совместимы.*

3.  **librdkafka (C/C++ клиент для Kafka, >= 1.x, рекомендуется последняя стабильная):**
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install librdkafka
        ```
    *   **Linux (apt):**
        ```bash
        sudo apt-get install librdkafka-dev
        ```

4.  **librabbitmq-c (C клиент для RabbitMQ, >= 0.8.0, рекомендуется последняя стабильная):**
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install librabbitmq # Может называться rabbitmq-c в vcpkg
        ```
    *   **Linux (apt):**
        ```bash
        sudo apt-get install librabbitmq-dev
        ```

5.  **nlohmann-json (JSON для C++, >= 3.x, рекомендуется последняя стабильная):**
    *   Header-only библиотека.
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install nlohmann-json
        ```
    *   **Linux (apt):**
        ```bash
        sudo apt-get install nlohmann-json3-dev
        ```

6.  **Catch2 (фреймворк для C++ юнит-тестов, v3.x рекомендуется):**
    *   **Windows (vcpkg):**
        ```bash
        vcpkg install catch2
        ```
    *   **Linux (apt):**
        ```bash
        sudo apt-get install catch2 # Убедитесь, что это версия 3.x
        ```
        *Если системный менеджер пакетов предоставляет старую версию Catch2, ее можно скачать с GitHub и интегрировать через CMake FetchContent или установить вручную.*

**Примечания для Windows при использовании vcpkg:**
*   После установки `vcpkg`, интегрируйте его с вашей средой сборки (например, Visual Studio) командой: `vcpkg integrate install`. Это позволит CMake автоматически находить установленные библиотеки.
*   При конфигурировании CMake проекта (например, через GUI CMake или в командной строке), вам нужно будет указать путь к файлу `vcpkg.cmake` через переменную `CMAKE_TOOLCHAIN_FILE`:
    ```bash
    cmake -B build -S . -DCMAKE_TOOLCHAIN_FILE=[путь_к_vcpkg]/scripts/buildsystems/vcpkg.cmake
    ```
*   Если вы не используете `vcpkg integrate install`, вам может потребоваться явно указать пути к библиотекам в CMake.

**Установка `protoc` и `grpc_cpp_plugin` на Windows (если не через vcpkg gRPC):**
*   Скачайте pre-compiled бинарные файлы `protoc` (например, `protoc-xxx-win64.zip`) с GitHub репозитория Protocol Buffers. Распакуйте и добавьте путь к `bin` каталогу в `PATH`.
*   `grpc_cpp_plugin` обычно собирается как часть gRPC. Если вы собираете gRPC из исходников, убедитесь, что плагин собран и его путь также доступен CMake (либо находится рядом с `protoc`, либо путь к нему указан явно). Пользователи vcpkg обычно получают его автоматически с `vcpkg install grpc`.

## Installation

### 1. Клонирование репозитория
```bash
git clone <URL_вашего_репозитория>
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
        .env\Scriptsctivate
        ```
*   **Установка Python зависимостей:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Установка C++ зависимостей
Процесс установки C++ зависимостей подробно описан в разделе [C++ Development](#c-development) выше. Убедитесь, что все перечисленные там компоненты установлены согласно инструкциям для вашей операционной системы (особенно для Windows с использованием `vcpkg`).

**Краткое напоминание для Windows с `vcpkg`:**
1.  Установите `vcpkg` согласно официальной документации.
2.  Установите необходимые библиотеки:
    ```bash
    vcpkg install boost-asio boost-system boost-program-options grpc librdkafka librabbitmq nlohmann-json catch2
    ```
3.  Интегрируйте `vcpkg` с вашей системой сборки:
    ```bash
    vcpkg integrate install
    ```
    Это позволит CMake автоматически находить библиотеки, установленные через `vcpkg`.

### 4. Генерация gRPC кода
Перед сборкой C++ компонентов необходимо сгенерировать код из `.proto` файлов. CMake настроен на автоматическую генерацию этого кода, если `protoc` и `grpc_cpp_plugin` установлены и доступны.

*   Убедитесь, что `protoc` (компилятор Protocol Buffers) и `grpc_cpp_plugin` (плагин gRPC для C++) установлены и находятся в системном `PATH` или их пути известны CMake. См. раздел [C++ Development](#c-development) для деталей установки.
*   Проект `cpp/protos/CMakeLists.txt` отвечает за генерацию кода. Он будет автоматически запущен при сборке C++ части проекта.

### 5. Сборка C++ компонентов
Сборка C++ компонентов осуществляется с помощью CMake.

**Общий процесс (из корневого каталога проекта):**
1.  Перейдите в каталог `cpp`:
    ```bash
    cd cpp
    ```
2.  Создайте каталог для сборки (например, `build`):
    ```bash
    mkdir build
    cd build
    ```

**Конфигурация и сборка для Linux/macOS (GCC/Clang):**
```bash
# Находясь в cpp/build/
cmake ..
make -j$(nproc) # Используйте количество ядер вашего процессора
```

**Конфигурация и сборка для Windows (Visual Studio с использованием `vcpkg`):**

*   **Предварительно:** Убедитесь, что `vcpkg integrate install` был выполнен.
*   **Конфигурация (генерация проекта Visual Studio):**
    Откройте PowerShell или Developer Command Prompt for Visual Studio. Находясь в каталоге `cpp/build/`, выполните:
    ```powershell
    cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_TOOLCHAIN_FILE=[путь_к_vcpkg]/scripts/buildsystems/vcpkg.cmake
    ```
    *   Замените `"Visual Studio 17 2022"` на вашу версию Visual Studio (например, `"Visual Studio 16 2019"`). Узнать доступные генераторы можно командой `cmake --help`.
    *   `-A x64` указывает на сборку под 64-битную архитектуру (можно изменить на `Win32` для 32-битной).
    *   Замените `[путь_к_vcpkg]` на актуальный путь к вашему экземпляру `vcpkg`.
*   **Сборка:**
    *   **Через CMake:**
        ```powershell
        cmake --build . --config Release # или Debug
        ```
        Эта команда соберет проект с конфигурацией Release (или Debug).
    *   **Через Visual Studio IDE:**
        Откройте сгенерированный файл решения (`.sln`) в каталоге `cpp/build/` с помощью Visual Studio. Затем выберите конфигурацию (Debug/Release) и платформу (x64/Win32) и соберите решение (Build -> Build Solution).

**Результаты сборки:**
Исполняемые файлы для C++ сервера аутентификации, игрового сервера и тестов будут находиться в соответствующих подкаталогах внутри `cpp/build/` (например, `cpp/build/auth_server_cpp/Release/auth_server_app.exe` и `cpp/build/game_server_cpp/Release/game_server_app.exe` для Windows Release сборки, или `cpp/build/auth_server_cpp/auth_server_app` для Linux).

### 6. Установка Docker (для инфраструктурных сервисов)
Если вы планируете запускать инфраструктурные сервисы (Kafka, RabbitMQ, Redis) с помощью Docker, убедитесь, что Docker и Docker Compose установлены.
*   **Docker Desktop для Windows/macOS:** Скачайте с официального сайта Docker.
*   **Docker для Linux:** Следуйте инструкциям на официальном сайте Docker для вашего дистрибутива.

## Running the Application

Рекомендуется запускать базовые сервисы (Kafka, RabbitMQ, Redis) с использованием Docker для упрощения настройки.

### 1. Запуск базовой инфраструктуры (Docker)
В корне проекта находится файл `docker-compose.yml`, который сконфигурирован для запуска необходимых сервисов.
```bash
# Находясь в корневом каталоге проекта
docker-compose up -d kafka rabbitmq redis
```
*   Эта команда запустит Kafka, RabbitMQ и Redis в фоновом режиме (`-d`).
*   Убедитесь, что Docker Desktop (для Windows/macOS) или Docker Engine (для Linux) запущен.
*   Для просмотра логов сервисов: `docker-compose logs -f kafka rabbitmq redis`.
*   Для остановки сервисов: `docker-compose down`.

### 2. Настройка переменных окружения
Многие компоненты приложения используют переменные окружения для конфигурации (порты, адреса хостов для Kafka/Redis и т.д.). Ниже приведен список основных переменных и их значений по умолчанию. Вы можете переопределить их перед запуском сервисов.

**Общие для нескольких сервисов:**
*   `REDIS_HOST`: Адрес хоста Redis (по умолчанию: `localhost`).
*   `REDIS_PORT`: Порт Redis (по умолчанию: `6379`).
*   `KAFKA_BOOTSTRAP_SERVERS`: Список брокеров Kafka (по умолчанию: `localhost:9092`).
*   `RABBITMQ_HOST`: Адрес хоста RabbitMQ (по умолчанию: `localhost`).
*   `RABBITMQ_PORT`: Порт RabbitMQ (по умолчанию: `5672`).
*   `RABBITMQ_USER`: Пользователь RabbitMQ (по умолчанию: `user`, если настроено в `docker-compose.yml`).
*   `RABBITMQ_PASS`: Пароль RabbitMQ (по умолчанию: `password`, если настроено в `docker-compose.yml`).

**Для Python Auth gRPC Service (`auth_server`):**
*   `AUTH_GRPC_PYTHON_PORT`: Порт для gRPC сервиса аутентификации (по умолчанию: `50051`).
*   `LOG_LEVEL`: Уровень логирования (например, `INFO`, `DEBUG`).

**Для C++ TCP Auth Server (`auth_server_cpp`):**
*   Принимает порт и адрес gRPC сервиса как аргументы командной строки.
    *   Порт TCP сервера: (например, `9000`).
    *   Адрес Python Auth gRPC Service: (например, `localhost:50051`).
*   Переменные окружения напрямую не используются для базовой конфигурации в текущей реализации `main_auth.cpp`, но могут быть добавлены.

**Для C++ Game Server (`game_server_cpp`):**
*   `GAME_SERVER_CPP_TCP_PORT`: Порт для TCP соединений игрового сервера (например, `8888`, если не задан, используется значение по умолчанию из кода).
*   `GAME_SERVER_CPP_UDP_PORT`: Порт для UDP соединений игрового сервера (например, `8889`, если не задан, используется значение по умолчанию из кода).
*   `AUTH_GRPC_SERVICE_ADDRESS`: Адрес Python Auth gRPC Service для валидации токенов (например, `localhost:50051`).
*   `TANK_POOL_SIZE`: Размер пула танков (например, `50`).
*   (Другие переменные для Kafka, RabbitMQ, если они не жестко закодированы и читаются из окружения в C++ коде).

**Установка переменных окружения:**
*   **Linux/macOS (в текущей сессии терминала):**
    ```bash
    export REDIS_HOST=localhost
    export AUTH_GRPC_PYTHON_PORT=50051
    # и так далее
    ```
*   **Windows (CMD - в текущей сессии):**
    ```cmd
    set REDIS_HOST=localhost
    set AUTH_GRPC_PYTHON_PORT=50051
    # и так далее
    ```
*   **Windows (PowerShell - в текущей сессии):**
    ```powershell
    $env:REDIS_HOST = "localhost"
    $env:AUTH_GRPC_PYTHON_PORT = "50051"
    # и так далее
    ```
Для постоянной установки переменных окружения используйте настройки вашей ОС.

### 3. Запуск сервисов локально (порядок важен)
Перед запуском убедитесь, что выполнены шаги из раздела [Installation](#installation), включая настройку Python окружения и сборку C++ компонентов.

**Активируйте Python виртуальное окружение, если еще не сделали этого:**
*   Linux/macOS: `source venv/bin/activate`
*   Windows: `.env\Scriptsctivate`

**a. Python Auth gRPC Service (`auth_server`):**
Откройте терминал в корневом каталоге проекта.
*   **Linux/macOS:**
    ```bash
    export AUTH_GRPC_PYTHON_PORT=50051
    export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
    export REDIS_HOST=localhost
    export REDIS_PORT=6379
    # Добавьте другие необходимые переменные окружения
    python -m auth_server.auth_grpc_server
    ```
*   **Windows (PowerShell):**
    ```powershell
    $env:AUTH_GRPC_PYTHON_PORT = "50051"
    $env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    $env:REDIS_HOST = "localhost"
    $env:REDIS_PORT = "6379"
    # Добавьте другие необходимые переменные окружения
    python -m auth_server.auth_grpc_server
    ```
    Сервис должен запуститься и слушать порт, указанный в `AUTH_GRPC_PYTHON_PORT`.

**b. C++ TCP Auth Server (`auth_server_cpp`):**
Откройте новый терминал.
*   **Путь к исполняемому файлу:**
    *   Linux/macOS: `cpp/build/auth_server_cpp/auth_server_app`
    *   Windows (Release): `cpp\build\auth_server_cpp\Release\auth_server_app.exe`
    *   Windows (Debug): `cpp\build\auth_server_cpp\Debug\auth_server_app.exe`
*   **Запуск (пример для Release сборки на Windows):**
    ```powershell
    # Находясь в корневом каталоге проекта
    # Первый аргумент - порт для этого C++ TCP сервера, второй - адрес Python gRPC сервиса
    .\cppuilduth_server_cpp\Releaseuth_server_app.exe 9000 localhost:50051
    ```
    *   Замените `9000` на желаемый порт для C++ TCP Auth Server.
    *   Замените `localhost:50051` на актуальный адрес и порт запущенного Python Auth gRPC Service.

**c. C++ Game Server (`game_server_cpp`):**
Откройте новый терминал.
*   **Путь к исполняемому файлу:**
    *   Linux/macOS: `cpp/build/game_server_cpp/game_server_app`
    *   Windows (Release): `cpp\build\game_server_cpp\Release\game_server_app.exe`
    *   Windows (Debug): `cpp\build\game_server_cpp\Debug\game_server_app.exe`
*   **Запуск (пример для Release сборки на Windows):**
    Установите переменные окружения (если C++ код их использует) или передайте конфигурацию через аргументы командной строки, если это поддерживается.
    ```powershell
    # Находясь в корневом каталоге проекта
    $env:GAME_SERVER_CPP_TCP_PORT = "8888"
    $env:GAME_SERVER_CPP_UDP_PORT = "8889"
    $env:AUTH_GRPC_SERVICE_ADDRESS = "localhost:50051" # Адрес Python Auth gRPC Service
    $env:RABBITMQ_HOST = "localhost"
    $env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    # Добавьте другие необходимые переменные
    .\cppuild\game_server_cpp\Release\game_server_app.exe
    ```
    *   Убедитесь, что `AUTH_GRPC_SERVICE_ADDRESS` указывает на работающий Python Auth gRPC Service.
    *   Текущая реализация `game_server_cpp/main.cpp` может использовать как переменные окружения (для некоторых параметров), так и жестко закодированные значения или аргументы командной строки. Проверьте исходный код `main.cpp` для точных методов конфигурации.

### 4. Запуск с использованием основного Docker Compose (для Python сервисов)
Основной файл `docker-compose.yml` в корне проекта может быть использован для сборки и запуска Python сервисов (например, `auth_service`).
**Примечание:** Текущий `docker-compose.yml` может не включать инструкции для сборки и запуска C++ компонентов. Для полного запуска всех сервисов через Docker Compose потребуется его доработка.

**Запуск Python сервисов из `docker-compose.yml`:**
```bash
# Находясь в корневом каталоге проекта
docker-compose up --build auth-service # Пример имени сервиса из docker-compose.yml
```
*   `--build` пересобирает образ перед запуском.
*   Используйте `docker-compose logs -f auth-service` для просмотра логов.

Для полноценного развертывания всего приложения с использованием Docker, включая C++ сервисы, необходимо:
1.  Создать или доработать `Dockerfile` для каждого C++ сервиса (например, `cpp/auth_server_cpp/Dockerfile`, `cpp/game_server_cpp/Dockerfile`). Эти Dockerfile должны описывать сборку C++ приложений в контейнере.
2.  Добавить соответствующие сервисы в основной `docker-compose.yml`, указав `build` контекст на каталоги с C++ Dockerfile.
3.  Настроить зависимости между сервисами (`depends_on`) в `docker-compose.yml`.

## Testing

В проекте предусмотрены различные виды тестов для Python и C++ компонентов. Перед запуском тестов убедитесь, что все необходимые зависимости установлены (см. разделы [Requirements](#requirements) и [Installation](#installation)) и, если требуется, базовые сервисы (Kafka, Redis, RabbitMQ) запущены (см. [Запуск базовой инфраструктуры](#1-запуск-базовой-инфраструктуры-docker)).

### Python Тесты

Python тесты используют `pytest`. Убедитесь, что вы находитесь в активированном виртуальном окружении Python (`source venv/bin/activate` или `.\venv\Scripts\activate`).

**1. Установка тестовых зависимостей (если еще не установлены):**
```bash
pip install pytest pytest-asyncio locust
# Другие зависимости, если они специфичны для тестов и не включены в основной requirements.txt
```

**2. Запуск всех Python тестов (юнит и интеграционных):**
Скрипт `run_tests.sh` предназначен для Linux/macOS. На Windows команды нужно выполнять вручную.

*   **Linux/macOS:**
    ```bash
    ./run_tests.sh # Этот скрипт может содержать команды ниже
    ```
*   **Windows (CMD/PowerShell):**
    Перейдите в корневой каталог проекта.
    ```powershell
    # Запуск всех тестов, обнаруженных pytest (включая unit и integration)
    pytest -v
    ```
    Или можно указать конкретные каталоги/файлы:
    ```powershell
    # Только юнит-тесты
    pytest -v tests/unit/

    # Только интеграционные тесты
    pytest -v tests/test_integration.py tests/test_auth_server.py tests/test_game_server.py
    ```
    *   Флаг `-v` (verbose) выводит более подробную информацию о ходе выполнения тестов.
    *   Для некоторых интеграционных тестов может потребоваться запуск соответствующих сервисов (например, Python Auth gRPC Service, C++ Game Server).

**3. Python Юнит-тесты:**
Тестируют отдельные модули и функции изолированно.
*   **Расположение:** `tests/unit/`
*   **Запуск (из корневого каталога проекта):**
    *   Linux/macOS: `pytest -v tests/unit/`
    *   Windows: `pytest -v tests\unit\`

**4. Python Интеграционные тесты:**
Тестируют взаимодействие между несколькими компонентами системы.
*   **Расположение:** `tests/test_integration.py`, `tests/test_auth_server.py`, `tests/test_game_server.py`
*   **Запуск (из корневого каталога проекта):**
    *   Linux/macOS: `pytest -v tests/test_integration.py` (и другие файлы)
    *   Windows: `pytest -v tests\test_integration.py` (и другие файлы)
*   **Важно:** Перед запуском интеграционных тестов убедитесь, что все необходимые внешние сервисы (Redis, Kafka, RabbitMQ) и тестируемые приложения (например, Python Auth gRPC сервис) запущены и доступны. См. раздел [Running the Application](#running-the-application).

**5. Python Нагрузочные тесты (Locust):**
Используются для измерения производительности сервисов под нагрузкой.
*   **Расположение файлов сценариев:** `tests/load/` (например, `locustfile_auth.py`, `locustfile_game.py`).
*   **Запуск:**
    1.  Убедитесь, что целевой сервис (например, Python Auth gRPC Service или C++ Game Server) запущен и доступен по сети.
    2.  Откройте терминал (с активированным Python venv).
    3.  Перейдите в каталог `tests/load/`.
    4.  Запустите Locust, указав файл сценария и хост тестируемого сервиса.

    *   **Пример для тестирования Python Auth gRPC Service (предполагается, что он доступен через какой-то HTTP прокси или напрямую, если Locust сконфигурирован для gRPC):**
        Если `auth_server` (Python TCP, устаревший) запущен на `localhost:8888` (как в старом README):
        ```bash
        # Находясь в tests/load/
        locust -f locustfile_auth.py --host=http://localhost:8888
        ```
        Если тестируется gRPC сервис, locust должен использовать gRPC клиент. Сценарии в `tests/load/` должны быть соответствующим образом адаптированы. Стандартный `--host` для HTTP. Для gRPC см. [Locust gRPC documentation](https://docs.locust.io/en/stable/testing-other-systems.html#grpc).
        Предположим, `locustfile_auth.py` адаптирован для gRPC и знает адрес `localhost:50051` (Python Auth gRPC Service). Команда может выглядеть так (специфично для реализации locust файла):
        ```bash
        # Находясь в tests/load/
        locust -f locustfile_auth.py # Конфигурация хоста gRPC внутри файла
        ```

    *   **Пример для тестирования C++ Game Server (TCP порт):**
        Предположим, C++ Game Server слушает TCP на `localhost:8888`.
        ```bash
        # Находясь в tests/load/
        locust -f locustfile_game.py --host=tcp://localhost:8888 # Уточните, как locustfile_game.py обрабатывает хост
        ```
        *Примечание: locust по умолчанию для HTTP. Для TCP/UDP или других протоколов, клиентская логика в `locustfile_*.py` должна быть соответствующей.*

    5.  После запуска Locust, откройте веб-интерфейс в браузере по адресу, указанному в консоли (обычно `http://localhost:8089`).
    6.  В интерфейсе укажите количество пользователей и скорость их появления, затем начните тест.

### C++ Юнит-тесты (Catch2)

C++ юнит-тесты написаны с использованием фреймворка Catch2 и интегрированы в систему сборки CMake.

**1. Сборка тестов:**
Тесты собираются вместе с остальными C++ компонентами (см. [Build C++ Components](#5-сборка-c-компонентов)). Исполняемый файл тестов обычно создается в каталоге `cpp/build/tests/` (например, `cpp/build/tests/game_tests` или `cpp/build/tests/cpp_tests.exe` на Windows).

**2. Запуск C++ тестов:**

*   **Способ 1: Через CTest (рекомендуется для CI и автоматизации):**
    CTest - это инструмент для запуска тестов, интегрированный с CMake.
    1.  Откройте терминал или PowerShell.
    2.  Перейдите в каталог сборки C++: `cd cpp/build`.
    3.  Запустите CTest:
        ```bash
        # Для подробного вывода (verbose)
        ctest -V
        ```
        Или для конкретной конфигурации на Windows:
        ```powershell
        # Находясь в cpp/build/
        ctest -C Debug -V # Запуск Debug тестов
        ctest -C Release -V # Запуск Release тестов
        ```
        CTest автоматически найдет и запустит все определенные в CMake тесты.

*   **Способ 2: Прямой запуск исполняемого файла тестов:**
    Вы можете напрямую запустить скомпилированный исполняемый файл тестов.
    *   **Linux/macOS:**
        ```bash
        # Находясь в cpp/build/
        ./tests/game_tests # Имя может отличаться, см. CMakeLists.txt в cpp/tests/
        ```
    *   **Windows (из каталога `cpp/build/`):**
        ```powershell
        # Для Release сборки
        .\tests\Release\cpp_tests.exe # Имя может отличаться
        # Для Debug сборки
        .\tests\Debug\cpp_tests.exe   # Имя может отличаться
        ```
        Исполняемый файл Catch2 предоставляет множество аргументов командной строки для выбора тестов, уровня детализации и т.д. Например, `./tests/game_tests --list-tests` покажет все доступные тесты.

**3. Зависимости для C++ тестов:**
*   Некоторые C++ тесты (например, `test_auth_tcp_session.cpp`, который тестирует взаимодействие C++ TCP Auth Server с Python Auth gRPC Service) могут требовать, чтобы **Python Auth gRPC Service был запущен** и доступен по адресу, указанному в конфигурации теста (обычно `localhost:50051`).
*   Убедитесь, что Python сервис запущен перед выполнением таких C++ тестов.

### Общие замечания по тестированию на Windows:

*   **Переменные окружения:** Убедитесь, что все необходимые переменные окружения установлены корректно, особенно `PATH` для доступа к компиляторам, CMake, `protoc`, `vcpkg` библиотекам и т.д.
*   **Пути к файлам:** Windows использует `\` в качестве разделителя пути, в то время как Linux/macOS используют `/`. Скрипты и команды должны это учитывать. В PowerShell часто можно использовать `/` взаимозаменяемо.
*   **Брандмауэр Windows:** При запуске сетевых сервисов или тестов, которые взаимодействуют по сети (например, Locust, интеграционные тесты), брандмауэр Windows может запросить разрешение на доступ. Предоставьте необходимые разрешения.
*   **Права доступа:** Некоторые операции могут требовать прав администратора, хотя это редкость для обычного запуска тестов.
*   **Кодировки:** Убедитесь, что файлы (особенно исходный код и конфигурационные файлы) сохранены в кодировке UTF-8 для избежания проблем с символами.
*   **Отладка тестов на Windows:**
    *   **Python:** Используйте отладчик вашей IDE (VS Code, PyCharm) для пошагового выполнения `pytest`.
    *   **C++:** Если вы сгенерировали проект Visual Studio, вы можете открыть его в VS IDE, установить исполняемый файл тестов в качестве запускаемого проекта и использовать встроенный отладчик Visual Studio. Установите точки останова в коде тестов или в тестируемом коде.

Эта секция должна предоставить исчерпывающее руководство по тестированию всех аспектов проекта на различных платформах, с особым вниманием к Windows.

## Contributing
Contributions are welcome! Please follow standard practices:
1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes.
4.  Add/update tests.
5.  Ensure all tests pass.
6.  Submit a pull request.

## Future Improvements
*   Complete the `docker-compose.yml` to include C++ services.
*   Implement robust configuration management for C++ services (e.g., using config files or more comprehensive environment variable parsing).
*   Expand C++ unit and integration tests, including mocks for external services.
*   Integrate C++ services with Prometheus for metrics.
*   Enhance game logic and features in the C++ game server.
*   Develop client applications.
