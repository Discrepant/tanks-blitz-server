# Серверная архитектура Tanks Blitz (Прототип)

Этот проект представляет собой прототип серверной архитектуры для многопользовательской игры Tanks Blitz, разработанный на Python.
Он включает компоненты для аутентификации, игровой логики, масштабирования, мониторинга и резервного копирования.

## Обзор проекта

Цель проекта - продемонстрировать построение серверной части для MMO-игры с учетом современных практик и технологий, таких как:
- Разделение сервисов (аутентификация, игра)
- Асинхронное программирование
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
    *   **Протокол: TCP, JSON.** Сервер принимает JSON-объекты. Каждое JSON-сообщение, отправляемое на сервер, **должно завершаться символом новой строки (`\n`)**.
    *   **Формат сообщений (JSON):**
        *   **Запрос на вход:** `{"action": "login", "username": "player1", "password": "password123"}`
        *   **Запрос на регистрацию (заглушка):** `{"action": "register", "username": "new_user", "password": "new_password"}`
        *   **Ответы сервера (JSON):**
            *   Успешный вход: `{"status": "success", "message": "User player1 authenticated", "session_id": "User player1 authenticated"}` (Примечание: `session_id` здесь для примера содержит сообщение, в реальной системе это был бы уникальный токен).
            *   Успешная регистрация (заглушка): `{"status": "success", "message": "Registration action received (mock)"}`
            *   Ошибка (неверный пароль, пользователь не найден): `{"status": "failure", "message": "Authentication failed: Invalid password"}` или `{"status": "failure", "message": "Authentication failed: User not found"}`
            *   Невалидный JSON: `{"status": "error", "message": "Invalid JSON format"}` (Сервер также логирует детали ошибки, например, `Ошибка декодирования JSON от <addr>: <JSONDecodeError details>. Получено: '<raw_json_string>'`)
            *   Ошибка кодировки: `{"status": "error", "message": "Invalid character encoding. UTF-8 expected."}` (Сервер логирует `Unicode decoding error from <addr>: <UnicodeDecodeError details>. Raw data: <raw_bytes>`)
            *   Неизвестное действие или отсутствующее поле `action`: `{"status": "error", "message": "Unknown or missing action"}`
    *   Назначение: Регистрация (в текущей реализации заглушка) и аутентификация пользователей. Ключевые модули включают `tcp_handler.py` для обработки соединений и команд, и `user_service.py` для логики работы с пользователями.
    *   Технологии: Python, `asyncio`.
    *   Экспортирует метрики для Prometheus на порт `8000`.
4.  **Игровой Сервер (Game Server):**
    *   **Протокол: UDP, сообщения в формате JSON.** Каждая UDP датаграмма должна содержать один JSON-объект. (Потенциально TCP может быть добавлен для управляющих команд или менее критичных данных, но текущая реализация фокусируется на UDP).
    *   **Формат сообщений (JSON):**
        *   Пример запроса на присоединение: `{"action": "join_game", "player_id": "some_player_id"}`
        *   Пример запроса на движение: `{"action": "move", "player_id": "some_player_id", "position": [10, 20]}`
        *   **Возможные ответы/ошибки от сервера (JSON, отправляются на адрес источника):**
            *   Успешное присоединение: `{"status": "joined", "session_id": "...", "tank_id": "...", "initial_state": {...}}`
            *   Ошибка присоединения (нет свободных танков): `{"status": "join_failed", "reason": "No tanks available"}`
            *   Невалидный JSON: `{"status": "error", "message": "Invalid JSON format"}` (Сервер логирует `Невалидный JSON получен от <addr>: '<raw_json_string>'`)
            *   Ошибка кодировки: `{"status": "error", "message": "Invalid character encoding. UTF-8 expected."}` (Сервер логирует `Unicode decoding error from <addr>: <UnicodeDecodeError details>. Raw data: <raw_bytes>`)
            *   Неизвестное действие: `{"status": "error", "message": "Unknown action"}` (Сервер логирует `Неизвестное действие '<action>' от игрока <player_id> (<addr>). Сообщение: <raw_json_string>`)
            *   Отсутствует `player_id` (когда требуется): Сервер логирует `Нет player_id в сообщении от <addr>. Сообщение: '<raw_json_string>'. Игнорируется.` и не отправляет ответ.
            *   Другие ошибки сервера: `{"status": "error", "message": "Internal server error: <error_type>"}`
        *   **Пустые сообщения:** Если сервер получает пустое сообщение (после удаления пробельных символов), он логирует это (`Received empty message from <addr> after strip. Ignoring.`) и игнорирует сообщение, не отправляя ответ.
    *   Назначение: Обработка игровой логики, синхронизация состояния игры. Ключевые модули: `udp_handler.py` для обработки основных игровых команд по UDP, `session_manager.py` для управления игровыми сессиями, и `tank_pool.py` для эффективного управления объектами танков.
    *   Паттерны:
        *   `SessionManager` (Singleton) для управления активными игровыми сессиями.
        *   `TankPool` (Object Pool) для управления объектами танков.
    *   Дельта-обновления: Концептуально заложены, но требуют полной реализации.
    *   Технологии: Python, `asyncio`.
    *   Экспортирует метрики для Prometheus на порт `8001`.
5.  **Redis:**
    *   Назначение: Кэширование, хранение временных данных сессий (если необходимо).
    *   Persistence: Настроен для RDB снапшотов и AOF логов.
    *   Резервное копирование: Автоматизировано через Kubernetes CronJob.
6.  **Prometheus:**
    *   Сбор метрик со всех серверных компонентов.
7.  **Grafana:**
    *   Визуализация метрик из Prometheus, создание дашбордов.
8.  **База данных (PostgreSQL - концептуально):**
    *   Предполагается для хранения данных пользователей, но в текущем прототипе сервер аутентификации использует заглушку (`MOCK_USERS_DB`). Для полноценной реализации потребуется интеграция с реальной БД.

### Структура проекта

- `auth_server/`: Код сервера аутентификации.
  - `main.py`: Точка входа, запуск TCP-сервера.
  - `tcp_handler.py`: Логика обработки TCP-соединений и команд.
  - `user_service.py`: Логика аутентификации (сейчас заглушка).
  - `metrics.py`: Определения метрик Prometheus.
- `game_server/`: Код игрового сервера.
  - `main.py`: Точка входа, запуск UDP-сервера.
  - `udp_handler.py`: Логика обработки UDP-пакетов и игровой логики.
  - `session_manager.py`: Управление игровыми сессиями (Singleton).
  - `tank_pool.py`: Управление объектами танков (Object Pool).
  - `tank.py`: Класс, представляющий танк.
  - `metrics.py`: Определения метрик Prometheus.
- `core/`: Общие модули (например, `redis_client.py`).
- `tests/`: Юнит и нагрузочные тесты.
  - `unit/`: Юнит-тесты (`pytest`).
  - `load/`: Нагрузочные тесты (`locust`).
- `monitoring/`: Конфигурации для Prometheus (`prometheus.yml`) и Grafana.
- `deployment/`: Dockerfile, скрипты и манифесты Kubernetes, конфигурации Nginx и Redis.
- `README.md`: Этот файл.
- `requirements.txt`: Зависимости Python.
- `docker-compose.yml`: Для локального запуска Prometheus и Grafana.

## Требования

- Python 3.9+
- Docker
- `kubectl` (для развертывания в Kubernetes)
- Доступ к кластеру Kubernetes (например, Minikube, Kind, или облачный EKS, GKE, AKS)
- `locust` (для запуска нагрузочных тестов)
- `netcat` (`nc`) или `telnet` (для ручного тестирования TCP/UDP)

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Локальный запуск серверов (для разработки)

**Сервер аутентификации:**
```bash
python -m auth_server.main
```
Сервер будет доступен по TCP на `localhost:8888`. Метрики Prometheus на `http://localhost:8000/metrics`.

**Игровой сервер:**
```bash
python -m game_server.main
```
Сервер будет доступен по UDP на `localhost:9999`. Метрики Prometheus на `http://localhost:8001/metrics`.

## Ручное тестирование и отладка

### Общие советы по отладке (Если ошибки остаются):
- **Проверяйте логи серверов:** Это первый и самый важный шаг. Серверы настроены на подробное логирование (уровень DEBUG). Вся активность, ошибки, полученные данные (включая сырые байты при ошибках декодирования) и отправленные ответы должны там отображаться.
- **Формат данных:**
    - **Auth Server (TCP):** Ожидает JSON, каждое сообщение **завершается символом новой строки (`\n`)**.
    - **Game Server (UDP):** Ожидает JSON в каждой UDP датаграмме.
- **Кодировка (UTF-8):**
    - Все текстовые данные, особенно строки внутри JSON, должны быть в кодировке UTF-8.
    - Если вы получаете от сервера ошибку `{"status": "error", "message": "Invalid character encoding. UTF-8 expected."}`, это означает, что клиент отправил данные в неверной кодировке (например, Windows-1251). Убедитесь, что ваш инструмент/клиент отправляет данные в UTF-8.
- **Проверка портов:** Убедитесь, что порты (8888 для Auth TCP, 9999 для Game UDP, 8000/8001 для метрик) не заняты другими приложениями.
  ```bash
  # Для Windows (PowerShell)
  Get-NetTCPConnection -LocalPort 8888
  Get-NetUDPEndpoint -LocalPort 9999
  # Или более универсально:
  netstat -ano | findstr :8888
  netstat -ano | findstr :9999
  ```
  Если порт занят, определите PID процесса и завершите его (например, через Диспетчер задач или командой `taskkill /PID <PID> /F` в Windows).
  ```powershell
  # Пример поиска PID и завершения процесса в PowerShell (используйте с осторожностью!)
  # $connection = Get-NetTCPConnection -LocalPort 8888
  # if ($connection) { 
  #   echo "Port 8888 is used by PID $($connection.OwningProcess)"
  #   # taskkill /F /PID $($connection.OwningProcess) 
  # } else { echo "Port 8888 is free." }
  ```
  ```bash
  # Для Linux/macOS
  sudo netstat -tulnp | grep :8888
  sudo netstat -tulnp | grep :9999
  # Если порт занят, используйте kill <PID>
  ```
- **Сетевой анализатор (Wireshark):** Мощный инструмент для анализа сетевого трафика. Помогает увидеть, что именно передается по сети, включая заголовки, полезную нагрузку, и корректность символов новой строки для TCP. Особенно полезен при отладке проблем с кодировкой или форматом JSON, которые не очевидны из логов сервера.
- **Логгинг на стороне клиента:** Если вы разрабатываете клиент, добавьте в него подробный логгинг отправляемых данных (включая сырые байты, если возможно) и получаемых ответов.
- **Валидация JSON:** Перед отправкой JSON, особенно если он формируется вручную или сложным кодом, проверьте его корректность (синтаксис, типы данных) с помощью онлайн-валидатора (например, JSONLint) или встроенных средств вашего IDE/языка программирования.
- **Проверка метрик Prometheus:** Серверы экспортируют метрики, которые могут дать представление об их состоянии.
  ```bash
  # Для Auth Server (замените localhost, если сервер на другом хосте)
  curl http://localhost:8000/metrics 
  # Для Game Server
  curl http://localhost:8001/metrics
  ```
  Ищите метрики вроде `active_connections_auth`, `successful_auths_total`, `failed_auths_total`, `total_datagrams_received_game`, `total_players_joined_game`.

#### Частые ошибки JSON (`json.JSONDecodeError`) и обработка неверных запросов:
Сервер логирует ошибки декодирования JSON с указанием адреса клиента и полученных данных, что помогает в диагностике.
  - `json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`: Часто означает, что парсеру была передана пустая строка.
    - **TCP (Auth Server):** Может произойти, если было отправлено сообщение без данных перед символом новой строки (`\n`), или если соединение было закрыто до отправки данных. Сервер отвечает `{"status": "error", "message": "Invalid JSON format"}`.
    - **UDP (Game Server):** Сервер логирует получение пустого сообщения (`Received empty message from <addr> after strip. Ignoring.`) и игнорирует его, не отправляя ответ.
  - `json.JSONDecodeError: Unterminated string starting at...`: Внутри JSON-строки отсутствует закрывающая кавычка. Пример: `{"key": "value}`. Сервер вернет ошибку "Invalid JSON format".
  - `json.JSONDecodeError: Expecting property name enclosed in double quotes...`: Имена ключей в JSON должны быть в двойных кавычках. Пример неверного JSON: `{key: "value"}`. Правильно: `{"key": "value"}`. Сервер вернет ошибку "Invalid JSON format".
  - `json.JSONDecodeError: Extra data: ...`: После корректного JSON-объекта идут дополнительные символы. Пример: `{"key": "value"} лишний текст`.
    - **TCP (Auth Server):** Сервер читает данные до первого `\n`. Если после валидного JSON до `\n` есть еще данные, это может вызвать эту ошибку при парсинге, либо эти данные будут проигнорированы в зависимости от логики чтения. Убедитесь, что каждое JSON-сообщение отправляется как одна строка, завершающаяся одним символом новой строки.
- **Обработка некорректных запросов Auth Server (после успешного парсинга JSON):**
    - Если JSON валиден, но поле `action` отсутствует или содержит неизвестное значение, сервер ответит: `{"status": "error", "message": "Unknown or missing action"}`.
    - Если `action` корректный (например, "login"), но отсутствуют обязательные поля (например, `username` или `password`), поведение может зависеть от конкретной реализации `authenticate_user` (может вернуть ошибку аутентификации или специальное сообщение). В текущей реализации `user_service.py` это приведет к ошибке аутентификации.

### Проблемы с Nginx (для Kubernetes)
Если вы используете Kubernetes и Nginx в качестве Ingress или LoadBalancer:
- **Проверьте конфигурацию Nginx:** Убедитесь, что ваш `nginx_configmap.yaml` (или аналогичный файл конфигурации Nginx) корректно настроен для проксирования TCP и UDP трафика на соответствующие сервисы Kubernetes.
  Пример для `stream` блока (обычно в `nginx.conf`, который может быть частью ConfigMap):
  ```nginx
  stream {
      upstream auth_backend {
          server auth-server-service:8888; # Имя сервиса Kubernetes и порт Auth Server
      }

      upstream game_backend {
          server game-server-service:9999; # Имя сервиса Kubernetes и порт Game Server
      }

      server {
          listen 8888; # Внешний TCP порт для Auth Server
          proxy_pass auth_backend;
      }

      server {
          listen 9999 udp; # Внешний UDP порт для Game Server
          proxy_pass game_backend;
      }
      # ... другие stream серверы, если нужны ...
  }
  ```
  **Важно:** Имена `auth-server-service` и `game-server-service` должны соответствовать именам ваших Kubernetes Services для Auth и Game серверов.
- **Проверьте доступность сервисов Kubernetes:**
  ```bash
  kubectl get services
  # Убедитесь, что сервисы auth-server-service и game-server-service существуют, 
  # имеют правильные порты и селекторы подов.
  kubectl get pods -l <label_selector_для_ваших_подов> 
  # Проверьте, что поды серверов запущены и работают.
  kubectl logs <имя_пода_nginx> -n <namespace_nginx>
  # Проверьте логи Nginx на предмет ошибок подключения к upstream'ам.
  ```

### Тестирование Сервера Аутентификации (TCP)
- **Запустите сервер локально:** `python -m auth_server.main`
- **Способ 1: `netcat` (nc)**
  *Важно: Каждое JSON-сообщение должно быть на одной строке и завершаться символом новой строки (`\n`). Команда `echo` (в Linux/macOS) автоматически добавляет `\n`. Для Windows `echo` может вести себя иначе, или можно использовать `printf` в Git Bash / WSL.*
  *Используйте одинарные кавычки вокруг JSON в примерах для `echo`, чтобы предотвратить интерпретацию специальных символов оболочкой.*
  ```bash
  # Успешная аутентификация (данные из MOCK_USERS_DB в user_service.py)
  echo '{"action": "login", "username": "player1", "password": "password123"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "success", "message": "User player1 authenticated", "session_id": "User player1 authenticated"}

  # Попытка регистрации (заглушка)
  echo '{"action": "register", "username": "new_user", "password": "new_password"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "success", "message": "Registration action received (mock)"}
  
  # Неверный пароль
  echo '{"action": "login", "username": "player1", "password": "wrongpassword"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "failure", "message": "Authentication failed: Invalid password"}

  # Несуществующий пользователь
  echo '{"action": "login", "username": "nonexist", "password": "foo"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "failure", "message": "Authentication failed: User not found"}

  # Невалидный JSON (например, отсутствует обязательное поле `action` или синтаксическая ошибка)
  echo '{"user": "player1", "pass": "password123"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "error", "message": "Unknown or missing action"}
  
  echo '{"action": "login", username: "player1", "password": "password123"}' | nc localhost 8888
  # Ожидаемый ответ: {"status": "error", "message": "Invalid JSON format"}
  # В логах сервера будет более детальная ошибка json.JSONDecodeError.
  
  # Отправка данных в неправильной кодировке (пример для Linux/macOS, требует iconv)
  # echo '{"action": "login", "username": "тест", "password": "тест"}' | iconv -f UTF-8 -t KOI8-R | nc localhost 8888
  # Ожидаемый ответ: {"status": "error", "message": "Invalid character encoding. UTF-8 expected."}
  # В логах сервера будет ошибка UnicodeDecodeError.
  ```
- **Способ 2: `telnet`**
  ```bash
  telnet localhost 8888
  ```
  После подключения вставьте или напечатайте полную JSON-строку (например, `{"action": "login", "username": "player1", "password": "password123"}`) и **нажмите Enter** (это отправит символ новой строки).
  ```
  {"action": "login", "username": "player1", "password": "password123"}
  ```
  Для выхода из telnet обычно используется `Ctrl+]` (или `Ctrl+[` в некоторых клиентах), затем `quit` и Enter.

### Тестирование Игрового Сервера (UDP)
- **Запустите сервер локально:** `python -m game_server.main`
- **Способ 1: `netcat` (nc) для UDP**
  *Примечание: Для UDP `nc -u` (или `nc -uv` для verbose) отправляет пакет и обычно завершается. Некоторые версии `nc` (особенно на macOS) могут требовать `nc -uvz localhost 9999` или `nc -u localhost 9999 -w1` (таймаут) для корректной отправки и немедленного завершения. Ответы от сервера (если они предусмотрены для данного действия) или ошибки нужно смотреть в логах сервера или использовать более сложный клиент для их отлова.*
  ```bash
  # Присоединение игрока (замените player_id_test_udp на уникальный ID)
  echo '{"action": "join_game", "player_id": "player_id_test_udp"}' | nc -u localhost 9999
  # Ожидаемый ответ (если сервер отвечает на join, текущая реализация отвечает): 
  # {"status": "joined", "session_id": "...", "tank_id": "...", "initial_state": {...}}
  # Этот ответ может быть выведен в stdout, если nc его получит до таймаута, но это не гарантировано для UDP.
  # Надежнее проверять логи сервера Game Server на сообщение: "Игрок player_id_test_udp присоединился к сессии..."

  # Движение (замените player_id_test_udp)
  echo '{"action": "move", "player_id": "player_id_test_udp", "position": [10,20]}' | nc -u localhost 9999
  # На это действие сервер обычно не отвечает напрямую отправителю, а рассылает обновления состояния другим игрокам в сессии. Проверяйте логи сервера.

  # Невалидный JSON (например, одинарные кавычки вместо двойных для ключей)
  echo "{'action': 'shoot', 'player_id': 'player_id_test_udp'}" | nc -u localhost 9999
  # Ожидаемый ответ от сервера (если nc его поймает): {"status": "error", "message": "Invalid JSON format"}
  # Проверяйте также логи сервера Game Server на наличие `ERROR - Невалидный JSON получен от ('127.0.0.1', <порт_клиента>): '{'action': 'shoot', 'player_id': 'player_id_test_udp'}'`.

  # Отправка пустого сообщения (nc может не отправить ничего, если echo пустое)
  # echo "" | nc -u localhost 9999
  # Сервер должен залогировать "Received empty message from ('127.0.0.1', <порт_клиента>) after strip. Ignoring." и не ответить.
  ```
- **Способ 2: Python-скрипт (см. `tests/load/send_udp_test.py` для примера)**
  Адаптируйте скрипт `send_udp_test.py` для отправки специфичных UDP-сообщений и логирования ответов. Это более надежный способ тестирования UDP, чем `nc`, особенно для проверки асинхронных ответов или ответов, отправляемых на другой порт/адрес.

### Пример успешного тестирования (локальный запуск)

1.  **Запустите серверы** в отдельных терминалах:
    ```bash
    # Терминал 1: Сервер Аутентификации
    python -m auth_server.main
    ```
    ```bash
    # Терминал 2: Игровой Сервер
    python -m game_server.main
    ```

2.  **Проверьте, что порты слушаются** (опционально, используя команды из раздела "Проверка портов").

3.  **Отправьте запрос на аутентификацию** (в третьем терминале):
    ```bash
    echo '{"action": "login", "username": "player1", "password": "password123"}' | nc localhost 8888
    ```
    **Ожидаемый ответ в терминале:**
    ```json
    {"status": "success", "message": "User player1 authenticated", "session_id": "User player1 authenticated"}
    ```
    **В логах Auth Server:** Должны появиться сообщения о новом подключении, полученных данных, успешной аутентификации и отправленном ответе.

4.  **Отправьте команду на присоединение к игре** (в третьем терминале):
    ```bash
    # Замените "player_id_example" на ваш ID игрока
    echo '{"action": "join_game", "player_id": "player_id_example"}' | nc -u localhost 9999
    ```
    **Ожидаемый ответ в терминале:** Может появиться JSON-ответ вида `{"status":"joined", ...}`, но для UDP с `nc` это не всегда надежно отображается.
    **В логах Game Server (самое важное для UDP):**
    Должно появиться сообщение, подтверждающее присоединение игрока, например:
    `INFO - Игрок player_id_example присоединился к сессии <session_id> с танком <tank_id>`
    А также лог полученной датаграммы:
    `DEBUG - Получена UDP датаграмма от ('127.0.0.1', <порт_клиента>) ... декодировано: '{"action": "join_game", "player_id": "player_id_example"}'`

5.  **Проверьте метрики Prometheus** (опционально, в третьем терминале):
    ```bash
    curl http://localhost:8000/metrics # Auth Server
    # Ищите successful_auths_total, active_connections_auth
    curl http://localhost:8001/metrics # Game Server
    # Ищите total_datagrams_received_game, total_players_joined_game
    ```

Этот сценарий демонстрирует базовую работоспособность обоих серверов и их взаимодействие с клиентом через `netcat`.

## Сборка и запуск с Docker

1.  **Собрать Docker образ:**
    Замените `your_image_name` на желаемое имя образа.
    ```bash
    docker build -t your_image_name:latest .
    ```

2.  **Запустить контейнер сервера аутентификации:**
    ```bash
    docker run -p 8888:8888 -p 8000:8000 your_image_name:latest auth
    ```

3.  **Запустить контейнер игрового сервера:**
    ```bash
    docker run -p 9999:9999/udp -p 8001:8001 your_image_name:latest game
    ```

## Развертывание в Kubernetes

Все необходимые манифесты находятся в директории `deployment/kubernetes/`.

**Предварительные шаги:**

1.  **Настройте `kubectl`** для работы с вашим кластером Kubernetes.
2.  **Соберите и загрузите Docker образ** (`your_image_name:latest`) в репозиторий образов, доступный вашему кластеру Kubernetes (например, Docker Hub, AWS ECR, Google GCR). Обновите имя образа в файлах `*.deployment.yaml`.
    *   Если вы используете локальный кластер типа Minikube, вы можете собрать образ непосредственно в Docker-демоне Minikube: `eval $(minikube -p minikube docker-env)` перед `docker build`. В этом случае `imagePullPolicy: IfNotPresent` в Deployment'ах может быть достаточно.

**Порядок развертывания компонентов:**

(См. предыдущую версию README для детального порядка `kubectl apply ...`)
Порядок: ConfigMaps (Nginx, Redis) -> PVC (Redis) -> Redis (Deployment, Service) -> Приложения (Auth, Game Deployments & Services) -> Nginx (Deployment, Service).

**Доступ к сервисам:**
- После развертывания Nginx с `type: LoadBalancer`, внешний IP-адрес Nginx будет точкой входа для TCP (порт 8888) и UDP (порт 9999) трафика.
- Метрики серверов (Auth:8000, Game:8001) будут доступны внутри кластера через их сервисы или через Nginx, если настроить для них проксирование.

## Мониторинг (Prometheus и Grafana)

1.  **Развертывание Prometheus и Grafana (локально):**
    Используйте `docker-compose.yml` из корня проекта:
    ```bash
    docker-compose up -d
    ```
    *Примечание: Убедитесь, что в `monitoring/prometheus/prometheus.yml` правильно указаны адреса ваших локально запущенных серверов (например, `host.docker.internal:8000` если серверы на хосте, а Prometheus в Docker на Windows/Mac, или `localhost:8000` если используется `network_mode: host` на Linux).*

2.  **Настройка Grafana:**
    - Откройте Grafana: `http://localhost:3000` (логин/пароль по умолчанию: admin/admin).
    - Добавить Prometheus как источник данных (URL: `http://prometheus:9090`).
    - Импортировать или создать дашборды для визуализации метрик.

## Тестирование

В проекте используются модульные тесты для проверки корректности работы отдельных компонентов серверов.

### Запуск тестов

-   **Для запуска всех юнит-тестов** выполните команду из корневой директории проекта:
    ```bash
    python -m pytest -v tests/unit/
    ```
    (Примечание: в некоторых системах может потребоваться `python3` вместо `python`, или просто `pytest -v tests/unit/` если `pytest` находится в PATH).

-   **Для запуска тестов конкретного файла** (например, тестов для обработчика TCP сервера аутентификации):
    ```bash
    python -m pytest -v tests/unit/test_tcp_handler_auth.py
    ```

### Покрытие тестами

Тесты проверяют следующие аспекты:
- Корректность работы обработчиков входящих сообщений для TCP (сервер аутентификации) и UDP (игровой сервер).
- Логику аутентификации пользователей, включая успешные и неуспешные сценарии.
- Управление игровыми сессиями и пулом объектов танков (концептуально, если тесты для них детализированы).
- Обработку различных ошибочных ситуаций, таких как некорректный формат JSON, ошибки кодировки, отсутствующие или неверные данные в запросах.
- Поведение серверов при получении пустых или невалидных сообщений.

## Резервное копирование Redis

- Redis настроен на использование RDB снапшотов и AOF логов для персистентности.
- Kubernetes CronJob (`deployment/kubernetes/redis_backup_cronjob.yaml`) настроен для выполнения скрипта резервного копирования.
- **Важно:** Место для хранения бэкапов (`backup-target-storage` в CronJob) должно быть настроено на использование надежного внешнего хранилища.

## Дальнейшие улучшения и TODO

- **Полная интеграция базы данных (PostgreSQL)** для сервера аутентификации.
- **Реализация системы токенов** (JWT) для аутентификации и авторизации.
- **Детализированная реализация дельта-обновлений** на игровом сервере.
- **Более сложная игровая логика.**
- **Матчмейкинг.**
- **Защищенное хранение секретов** в Kubernetes.
- **Настройка HTTPS/TLS** для Nginx и эндпоинтов метрик.
- **Централизованный сбор и анализ логов** (ELK Stack, Grafana Loki).
- **Улучшение скриптов резервного копирования и тестирование восстановления.**
- **Helm-чарт** для упрощения развертывания.
