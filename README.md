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
    *   Назначение: Регистрация (в текущей реализации заглушка) и аутентификация пользователей.
    *   Технологии: Python, `asyncio`.
    *   Экспортирует метрики для Prometheus на порт `8000`.
4.  **Игровой Сервер (Game Server):**
    *   **Протокол: UDP, сообщения в формате JSON.** Каждая UDP датаграмма должна содержать один JSON-объект.
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
    *   Назначение: Обработка игровой логики, синхронизация состояния игры.
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

Качественное тестирование - ключевой аспект разработки надежного серверного программного обеспечения. В этом проекте применяется многоуровневый подход к тестированию, чтобы обеспечить корректность работы каждого компонента и их взаимодействия.

### Философия тестирования

Мы стремимся покрывать тестами все критически важные участки кода. Это включает в себя как отдельные функции (модульные тесты), так и взаимодействие между различными частями системы (интеграционные тесты). Нагрузочные тесты помогают убедиться, что система способна выдерживать ожидаемую нагрузку.

Разработчикам рекомендуется писать тесты для нового функционала и исправлений ошибок, а также поддерживать существующие тесты в актуальном состоянии.

### Типы тестов и их запуск

#### 1. Модульные тесты (Unit Tests)

*   **Цель:** Проверка корректности работы отдельных, изолированных компонентов системы (функций, классов, модулей). Например, тестирование логики аутентификации пользователя в `user_service.py` или управление пулом объектов танков в `tank_pool.py`.
*   **Расположение:** `tests/unit/`
*   **Инструмент:** `pytest`
*   **Запуск всех модульных тестов:**
    ```bash
    sh run_tests.sh
    ```
    Эта команда запускает все автоматизированные тесты, включая модульные и интеграционные (см. ниже).
    Или напрямую с помощью `pytest`:
    ```bash
    pytest -v tests/unit/
    ```
*   **Написание новых модульных тестов:**
    *   Тестовые файлы должны называться `test_*.py` или `*_test.py`.
    *   Тестовые функции должны называться `test_*`.
    *   Используйте утверждения (`assert`) для проверки ожидаемых результатов.
    *   Для получения дополнительной информации обратитесь к [документации pytest](https://docs.pytest.org/).

##### Стратегии модульного тестирования

При написании модульных тестов полезно придерживаться нескольких ключевых стратегий:

*   **Тестируйте один логический блок за раз:** Каждый тест должен быть сфокусирован на проверке одного конкретного аспекта поведения функции или метода. Это упрощает понимание теста и локализацию ошибок.
*   **Изолируйте тестируемый модуль:** Модульные тесты не должны зависеть от внешних систем, таких как базы данных, сетевые сервисы или файловая система. Для этого используются техники, такие как мокинг (см. ниже).
*   **Используйте паттерн AAA (Arrange, Act, Assert):**
    *   **Arrange (Подготовка):** На этом этапе вы настраиваете все необходимые условия для теста. Это может включать инициализацию объектов, установку значений переменных, создание мок-объектов.
    *   **Act (Действие):** На этом этапе вы выполняете тестируемый код – вызываете функцию или метод, поведение которого хотите проверить.
    *   **Assert (Проверка):** На этом этапе вы проверяете, что результат выполнения кода соответствует вашим ожиданиям. Используйте различные `assert` утверждения для сравнения фактического результата с ожидаемым.

##### Примеры модульных тестов

Ниже приведены концептуальные примеры, иллюстрирующие, как могли бы выглядеть модульные тесты для компонентов этого проекта. Фактические тесты находятся в директории `tests/unit/`.

**Пример 1: Тестирование функции из `auth_server/user_service.py`**

Предположим, в `user_service.py` есть функция `is_valid_username(username: str) -> bool`, которая проверяет валидность имени пользователя по каким-то критериям (например, длина, допустимые символы).

```python
# tests/unit/test_user_service.py (концептуальный пример)
from auth_server.user_service import is_valid_username

def test_is_valid_username_valid():
    # Arrange (Подготовка)
    username = "player123"
    # Act (Действие)
    result = is_valid_username(username)
    # Assert (Проверка)
    assert result is True

def test_is_valid_username_too_short():
    # Arrange
    username = "p1"
    # Act
    result = is_valid_username(username)
    # Assert
    assert result is False, "Имя пользователя слишком короткое"

def test_is_valid_username_invalid_chars():
    # Arrange
    username = "player!"
    # Act
    result = is_valid_username(username)
    # Assert
    assert result is False, "Имя пользователя содержит недопустимые символы"
```

**Пример 2: Тестирование метода класса из `game_server/tank.py`**

Предположим, класс `Tank` в `game_server/tank.py` имеет метод `take_damage(amount: int)`, который уменьшает здоровье танка.

```python
# tests/unit/test_tank.py (концептуальный пример)
from game_server.tank import Tank

def test_tank_take_damage_reduces_health():
    # Arrange
    initial_health = 100
    tank = Tank(tank_id="test_tank", initial_health=initial_health, position=[0,0])
    damage_amount = 20
    expected_health = initial_health - damage_amount
    
    # Act
    tank.take_damage(damage_amount)
    
    # Assert
    assert tank.health == expected_health

def test_tank_take_damage_health_does_not_go_below_zero():
    # Arrange
    tank = Tank(tank_id="test_tank", initial_health=10, position=[0,0])
    damage_amount = 20
    expected_health = 0
    
    # Act
    tank.take_damage(damage_amount) # Попытка нанести урон больше текущего здоровья
    
    # Assert
    assert tank.health == expected_health
```

##### Мокинг (Mocking) в модульных тестах

Мокинг – это процесс создания "заглушек" или "поддельных" объектов, которые имитируют поведение реальных зависимостей тестируемого модуля. Это ключевая техника для достижения изоляции в модульных тестах.

*   **Зачем нужен мокинг?**
    *   **Изоляция:** Позволяет тестировать модуль, не беспокоясь о поведении его зависимостей. Если тест падает, вы знаете, что проблема именно в тестируемом модуле, а не в его зависимости.
    *   **Контроль:** Мок-объекты полностью под вашим контролем. Вы можете настроить их так, чтобы они возвращали определенные значения, вызывали исключения или проверяли, как они были вызваны.
    *   **Скорость:** Замена медленных зависимостей (например, сетевых запросов или обращений к БД) на быстрые моки значительно ускоряет выполнение тестов.
    *   **Предсказуемость:** Устраняет непредсказуемость, связанную с внешними зависимостями (например, недоступность сетевого сервиса).

*   **Библиотека для мокинга:**
    В Python для мокинга широко используется модуль `unittest.mock`, который доступен в стандартной библиотеке и хорошо интегрируется с `pytest`. Основные инструменты – это классы `Mock`, `MagicMock` и декораторы/менеджеры контекста `patch`.

*   **Пример использования `patch`:**

    Предположим, у нас есть функция в `auth_server.user_service.py`, которая для проверки учетных данных обращается к внешней системе (например, LDAP или другой микросервис). В модульном тесте мы не хотим делать реальный сетевой вызов.

    ```python
    # auth_server/user_service.py (фрагмент)
    # def check_credentials_in_external_system(username, password):
    #     # ... делает реальный сетевой вызов ...
    #     # response = requests.post("http://external-auth.system/validate", ...)
    #     # return response.status_code == 200
    #     pass # Заглушка для примера

    # def authenticate_user_with_external_system(username, password):
    #     # ... какая-то логика ...
    #     is_valid_in_external = check_credentials_in_external_system(username, password)
    #     if is_valid_in_external:
    #         return True, "User authenticated by external system"
    #     else:
    #         return False, "External system authentication failed"
    #     pass # Заглушка для примера
    ```

    Теперь тест для `authenticate_user_with_external_system` с использованием мока для `check_credentials_in_external_system`:

    ```python
    # tests/unit/test_user_service_external.py (концептуальный пример)
    from unittest.mock import patch
    # Предполагаем, что функция находится в auth_server.user_service
    # from auth_server.user_service import authenticate_user_with_external_system 

    # Путь для patch должен быть тем, где объект ИЩЕТСЯ, а не где он ОПРЕДЕЛЕН.
    # Если user_service.py импортирует check_credentials_in_external_system из другого модуля,
    # путь может быть другим. Если она определена в том же модуле, то путь будет 'auth_server.user_service.check_credentials_in_external_system'

    @patch('auth_server.user_service.check_credentials_in_external_system')
    def test_authenticate_user_external_success(mock_check_external_credentials):
        # Arrange
        # Настраиваем мок-объект: он должен вернуть True при вызове
        mock_check_external_credentials.return_value = True 
        
        username = "testuser"
        password = "password"
        
        # Act
        # Вместо реальной функции будет вызван mock_check_external_credentials
        # authenticated, message = authenticate_user_with_external_system(username, password) # Закомментировано, т.к. функция-заглушка
        authenticated, message = (True, "User authenticated by external system") # Имитация вызова для примера

        # Assert
        assert authenticated is True
        assert message == "User authenticated by external system"
        # Проверяем, что мок-функция была вызвана с правильными аргументами
        mock_check_external_credentials.assert_called_once_with(username, password)

    @patch('auth_server.user_service.check_credentials_in_external_system')
    def test_authenticate_user_external_failure(mock_check_external_credentials):
        # Arrange
        mock_check_external_credentials.return_value = False # Имитируем неудачную проверку
        
        username = "testuser"
        password = "wrongpassword"
        
        # Act
        # authenticated, message = authenticate_user_with_external_system(username, password) # Закомментировано
        authenticated, message = (False, "External system authentication failed") # Имитация вызова для примера
        
        # Assert
        assert authenticated is False
        assert message == "External system authentication failed"
        mock_check_external_credentials.assert_called_once_with(username, password)

    # Другой способ использования patch - как менеджер контекста:
    def test_authenticate_user_external_exception_handling():
        with patch('auth_server.user_service.check_credentials_in_external_system') as mock_check:
            # Arrange
            # Имитируем, что внешний вызов вызывает исключение
            mock_check.side_effect = ConnectionError("Failed to connect to external system")
            
            username = "user"
            password = "password"

            # Act & Assert
            # Здесь мы бы проверяли, что authenticate_user_with_external_system
            # корректно обрабатывает это исключение (например, логирует и возвращает ошибку)
            # try:
            #     authenticate_user_with_external_system(username, password)
            # except ConnectionError:
            #     pass # Ожидаемое исключение
            # else:
            #     assert False, "ConnectionError was not raised or handled"
            pass # Заглушка для примера, т.к. тестируемый код не полностью реализован
    ```
    В этих примерах `patch` заменяет реальную функцию `check_credentials_in_external_system` на мок-объект. Мы можем указать, какое значение этот мок должен вернуть (`return_value`) или какое исключение возбудить (`side_effect`), а также проверить, как он был вызван (`assert_called_once_with`).

#### 2. Интеграционные тесты (Integration Tests)

*   **Цель:** Проверка взаимодействия между различными компонентами системы. Например, корректность обмена данными между игровым сервером и клиентом аутентификации, или взаимодействие сервиса с базой данных (в будущем).
*   **Расположение:** В основном в `tests/test_integration.py`. Могут быть и другие файлы, специфичные для тестируемых интеграций.
*   **Инструмент:** `pytest`
*   **Запуск интеграционных тестов:**
    На данный момент, интеграционные тесты могут требовать запущенных сервисов или специфической конфигурации. Пример запуска:
    ```bash
    pytest -v tests/test_integration.py
    ```
    *Примечание: Рекомендуется включить запуск интеграционных тестов в скрипт `run_tests.sh` после обеспечения необходимой среды для их выполнения (например, поднятие Docker-контейнеров с сервисами).*
*   **Написание новых интеграционных тестов:**
    *   Тесты должны имитировать реальные сценарии использования, где несколько компонентов работают вместе.
    *   Может потребоваться настройка окружения (например, запуск зависимых сервисов в Docker) перед выполнением тестов и очистка после.

##### Стратегии интеграционного тестирования

Интеграционные тесты проверяют, как различные части системы работают вместе. Ключевые моменты:

*   **Фокус на взаимодействии:** Основная цель – убедиться, что компоненты корректно обмениваются данными и вызывают друг друга в соответствии с ожидаемыми "контрактами" (API, форматы сообщений, последовательность вызовов).
*   **Определение границ:** Четко определите, какие компоненты участвуют в каждом интеграционном тесте. Старайтесь не делать интеграционные тесты слишком широкими (end-to-end), так как их становится сложнее писать, отлаживать и поддерживать. Вместо этого, тестируйте интеграцию между логически связанными группами компонентов.
*   **Примеры точек интеграции в проекте:**
    *   **Auth Server и его внутренний `user_service`:** Хотя `user_service` в данном прототипе является заглушкой, в реальной системе он мог бы взаимодействовать с базой данных. Интеграционный тест проверял бы, что `tcp_handler` корректно вызывает `user_service`, а тот, в свою очередь, правильно обращается к БД (или ее моку, если БД не является частью *данного* интеграционного теста).
    *   **Game Server и `auth_client`:** Игровой сервер может использовать `auth_client` для проверки токенов сессий на сервере аутентификации. Интеграционный тест мог бы проверить этот сценарий: Game Server получает запрос от клиента, обращается через `auth_client` к реальному (или тестовому двойнику) Auth Server, получает ответ и корректно его обрабатывает.
    *   **Серверы и Redis:** Если бы серверы активно использовали Redis для кэширования или хранения сессионных данных, интеграционные тесты могли бы проверять корректность записи, чтения и удаления данных из Redis.
*   **Управление окружением:** Интеграционные тесты часто требуют более сложной настройки окружения, чем модульные. Это может включать:
    *   Запуск реальных экземпляров зависимых сервисов (например, в Docker-контейнерах).
    *   Настройку конфигурационных файлов.
    *   Подготовку начальных данных в базах данных или кэшах.
    *   Очистку окружения после теста для обеспечения независимости тестов.
    Инструменты типа `docker-compose` могут быть полезны для управления окружением для интеграционных тестов. `pytest` также предоставляет механизмы фикстур (fixtures) с областями видимости `session` или `module` для управления таким окружением.

##### Пример концептуального интеграционного теста

Рассмотрим сценарий, где Игровой Сервер должен проверить сессию пользователя через Сервер Аутентификации. Файл `tests/test_integration.py` мог бы содержать тест, выполняющий следующие шаги (псевдокод):

```python
# tests/test_integration.py (концептуальный пример)
import pytest
import asyncio
# ... (импорты для запуска серверов или клиентов)

# Фикстура для запуска/остановки сервера аутентификации (может использовать subprocess или Docker)
@pytest.fixture(scope="module")
async def running_auth_server():
    # Код для запуска Auth Server в отдельном процессе/контейнере
    auth_process = await asyncio.create_subprocess_exec("python", "-m", "auth_server.main", ...)
    await asyncio.sleep(1) # Дать серверу время на запуск
    
    yield "localhost:8888" # Адрес запущенного сервера
    
    # Код для остановки Auth Server
    auth_process.terminate()
    await auth_process.wait()

# Фикстура для игрового сервера, который будет использовать auth_client для связи с running_auth_server
@pytest.fixture
async def game_server_with_auth(running_auth_server_address):
    # Настройка game_server так, чтобы его auth_client указывал на running_auth_server_address
    # ...
    # game_server_instance = GameServer(auth_service_address=running_auth_server_address)
    # await game_server_instance.start()
    # yield game_server_instance
    # await game_server_instance.stop()
    pass # Заглушка, т.к. требует реальной реализации запуска сервера

# Предположим, у нас есть функция для отправки команды на игровой сервер
async def send_command_to_game_server(server_instance, command):
    # ... (логика отправки команды и получения ответа)
    pass # Заглушка

@pytest.mark.asyncio
async def test_game_server_session_validation_flow(running_auth_server, game_server_with_auth):
    # Arrange:
    # 1. Auth Server уже запущен фикстурой running_auth_server.
    # 2. Game Server (настроенный на использование этого Auth Server) запущен фикстурой game_server_with_auth.
    # 3. (Предположим) На Auth Server есть валидный пользователь и сессия.
    #    Для реального теста может потребоваться сначала создать пользователя/сессию через API Auth Server.
    valid_session_id = "mock_valid_session_id" # Это должно быть получено от Auth Server
    player_id = "player_for_integration_test"

    # Act:
    # Имитируем действие игрока, требующее проверки сессии на Game Server.
    # Например, игрок пытается выполнить какое-то важное действие.
    # response = await send_command_to_game_server(
    # game_server_with_auth,
    #     {"action": "perform_secure_action", "player_id": player_id, "session_id": valid_session_id}
    # )
    
    # В данном прототипе Game Server не имеет прямого клиента к Auth Server для валидации сессий,
    # но если бы имел, здесь была бы логика вызова.
    # Вместо этого, представим, что auth_client внутри game_server делает запрос к Auth Server.

    # Assert:
    # Проверяем, что Game Server успешно обработал запрос,
    # что подразумевает успешную валидацию сессии через Auth Server.
    # assert response["status"] == "success" 
    
    # Дополнительно можно проверить логи Auth Server на предмет запроса валидации сессии,
    # или метрики, если они есть.
    
    # Пример проверки (если бы auth_client был моком в этом специфичном тесте,
    # но в "чистом" интеграционном тесте он был бы реальным):
    # game_server_with_auth.auth_client.validate_session.assert_called_once_with(valid_session_id)
    
    print(f"Концептуальный тест: Auth Server на {running_auth_server}, Game Server настроен.")
    assert True # Заглушка для прохождения теста

```
Этот пример показывает, как фикстуры `pytest` могут использоваться для управления жизненным циклом серверов. Реальный тест был бы сложнее и включал бы отправку настоящих сетевых запросов и проверку их результатов, а также состояния серверов (например, через логи или API).

Важно отметить, что написание и поддержка интеграционных тестов требуют больше усилий, чем модульных, из-за необходимости управлять окружением и потенциальной хрупкости тестов при изменении контрактов между сервисами. Поэтому их следует применять для проверки ключевых взаимодействий и пользовательских сценариев.

#### 3. Нагрузочные тесты (Load Tests)

*   **Цель:** Оценка производительности, стабильности и масштабируемости серверов под высокой нагрузкой, имитирующей большое количество одновременных пользователей или запросов.
*   **Расположение:** `tests/load/`
*   **Инструмент:** `Locust`
*   **Запуск нагрузочных тестов:**
    Нагрузочные тесты требуют, чтобы целевые серверы были запущены и доступны.

    1.  **Для сервера аутентификации (Auth Server):**
        *   Убедитесь, что Auth Server запущен (например, `python -m auth_server.main` или через Docker).
        *   Выполните команду:
            ```bash
            locust -f tests/load/locustfile_auth.py AuthUser --host <auth_server_host>
            ```
            Замените `<auth_server_host>` на адрес сервера (например, `localhost` или IP/хост Docker-контейнера). Если `--host` не указан, Locust будет использовать значение по умолчанию из locust-файла (если оно там определено).

    2.  **Для игрового сервера (Game Server):**
        *   Убедитесь, что Game Server запущен (например, `python -m game_server.main` или через Docker).
        *   Выполните команду:
            ```bash
            locust -f tests/load/locustfile_game.py GameUser --host <game_server_host>
            ```
            Замените `<game_server_host>` на адрес сервера.

    После запуска Locust, откройте веб-интерфейс (обычно `http://localhost:8089`) для настройки параметров нагрузки (количество пользователей, скорость появления новых пользователей) и мониторинга результатов.

##### Стратегии нагрузочного тестирования

Нагрузочное тестирование помогает понять, как система ведет себя под давлением. Основные цели и стратегии:

*   **Определение максимальной производительности (Capacity Testing):** Увеличение нагрузки до тех пор, пока время отклика не станет неприемлемым или не начнут появляться ошибки. Это помогает понять пределы текущей конфигурации.
*   **Поиск узких мест (Bottleneck Identification):** Анализ метрик сервера (CPU, память, сеть, I/O) и времени отклика под нагрузкой для выявления компонентов, которые первыми достигают своего предела и ограничивают общую производительность.
*   **Тестирование стабильности и выносливости (Soak/Endurance Testing):** Поддержание определенного уровня нагрузки (например, ожидаемой пиковой) в течение длительного времени для выявления проблем, связанных с утечками памяти, исчерпанием ресурсов или деградацией производительности со временем.
*   **Стресс-тестирование (Stress Testing):** Проверка поведения системы при экстремальных нагрузках, превышающих ожидаемые пиковые значения, или в условиях ограниченных ресурсов (например, мало памяти). Цель – посмотреть, как система восстанавливается после снятия стресса.
*   **Тестирование масштабируемости (Scalability Testing):** Оценка того, как добавление ресурсов (например, CPU, памяти, экземпляров сервиса) влияет на производительность и пропускную способность.

При использовании Locust для этих целей:
*   **Профили нагрузки:** Можно создавать различные профили нагрузки в Locust, изменяя количество пользователей (`--users`) и скорость их появления (`--spawn-rate`), а также распределение задач между пользователями.
*   **Мониторинг:** Внимательно следите за метриками, предоставляемыми Locust (количество запросов в секунду, время отклика, количество ошибок), а также за метриками на стороне сервера (через Prometheus и Grafana).

##### Краткий обзор структуры locust-файла

Файлы `locustfile_auth.py` и `locustfile_game.py` содержат определение поведения "виртуальных пользователей". Основные элементы:

*   **Класс пользователя (User Class):** Наследуется от `User`, `HttpUser` (для HTTP-сервисов) или другого специфичного для протокола класса. В данном проекте, так как используются кастомные TCP и UDP протоколы, базовый класс `User` используется вместе со своими клиентами.
    *   `locustfile_auth.py` использует `AuthUser(User)` с кастомным TCP-клиентом.
    *   `locustfile_game.py` использует `GameUser(User)` с кастомным UDP-клиентом.
*   **Задачи (`@task`):** Методы класса пользователя, декорированные `@task(N)`, определяют действия, которые будет выполнять виртуальный пользователь. `N` – это опциональный вес задачи, влияющий на частоту ее выбора.
    ```python
    # Пример из locustfile_auth.py
    from locust import User, task, between
    import socket
    import json
    import time
    import random

    class AuthClient:
        # ... (реализация TCP клиента) ...

    class AuthUser(User):
        wait_time = between(1, 3) # Пауза между выполнением задач
        
        def __init__(self, environment):
            super().__init__(environment)
            self.client = AuthClient(self.host) # self.host передается из командной строки

        def on_start(self):
            # Действия при старте виртуального пользователя (например, подключение)
            try:
                self.client.connect()
                print(f"AuthUser: Connected to {self.host}")
            except Exception as e:
                print(f"AuthUser: Failed to connect to {self.host}: {e}")
                # Можно остановить пользователя, если соединение критично
                # self.environment.runner.quit() 

        @task(1) # Пример задачи для логина
        def login_task(self):
            username = f"user_{random.randint(1, 10000)}"
            password = "password123"
            request_data = {"action": "login", "username": username, "password": password}
            try:
                response = self.client.send(request_data)
                # Здесь можно добавить проверки ответа и сообщить Locust об успехе/неудаче
                # self.environment.events.request.fire(request_type="tcp", name="login", response_time=..., response_length=..., exception=None, context={})
            except Exception as e:
                # self.environment.events.request.fire(request_type="tcp", name="login", response_time=..., response_length=..., exception=e, context={})
                print(f"Login task error: {e}")


        def on_stop(self):
            # Действия при остановке виртуального пользователя (например, отключение)
            self.client.close()
            print(f"AuthUser: Disconnected from {self.host}")
    ```
*   **`on_start` и `on_stop`:** Методы, которые выполняются при запуске и остановке каждого виртуального пользователя. Используются для подготовки (например, установка соединения) и очистки ресурсов.
*   **`wait_time`:** Определяет время ожидания пользователя между выполнением задач. `between(min, max)` задает случайный интервал.

Изучите файлы в `tests/load/` для полного понимания реализации нагрузочных тестов для серверов аутентификации и игрового сервера.

#### 4. Тестирование соединения и протокола (Connection & Protocol Tests)

*   **Цель:** Проверка базовой возможности подключения к серверам по TCP/UDP и корректности обмена сообщениями согласно протоколу.
*   **Инструменты:** `netcat` (`nc`), `telnet`, специализированные скрипты (например, `send_tcp_test.py`).
*   **Ручное тестирование:**
    Раздел "Ручное тестирование и отладка" в этом README содержит подробные инструкции по использованию `netcat` и `telnet` для отправки сообщений на серверы аутентификации и игровой сервер. Это полезно для быстрой проверки и отладки.
*   **Автоматизированные скрипты:**
    *   Скрипт `send_tcp_test.py` является примером того, как можно автоматизировать отправку TCP-сообщений на сервер аутентификации. Его можно адаптировать для различных сценариев тестирования.
    *   Аналогичные скрипты могут быть созданы для UDP-взаимодействия с игровым сервером.
    *   Эти скрипты могут быть полезны для создания более сложных тестовых сценариев, которые трудно выполнить вручную.

### Запуск всех тестов

Основной скрипт `run_tests.sh` был обновлен и теперь предназначен для запуска всех основных автоматизированных тестов, включая модульные и интеграционные. Это рекомендуемый способ для запуска полного набора проверок.

```bash
sh run_tests.sh
```

Скрипт `run_tests.sh` теперь включает запуск как `tests/unit/` (модульные тесты), так и `tests/test_integration.py` (интеграционные тесты).

Для дальнейшего расширения его функциональности (например, если интеграционные тесты потребуют сложной настройки окружения), скрипт `run_tests.sh` может быть доработан. Это может включать:
*   Управление зависимостями для тестов (например, запуск/остановка Docker-контейнеров, если интеграционные тесты их требуют).

### Важность написания тестов

Написание тестов для нового кода или при исправлении ошибок является важной частью процесса разработки. Это помогает:
*   Обеспечить корректность реализованной логики.
*   Предотвратить регрессии в будущем (когда изменения в одной части системы непреднамеренно ломают другую).
*   Улучшить дизайн кода, так как код, который легко тестировать, обычно является более модульным и слабосвязанным.
*   Облегчить рефакторинг и поддержку кода.

### Статический анализ кода (Linting)

Хотя это не является частью динамического тестирования (выполнения кода), статический анализ кода с помощью линтеров (таких как Flake8, Pylint, MyPy) настоятельно рекомендуется. Линтеры проверяют код на соответствие стандартам оформления (PEP 8), выявляют потенциальные ошибки, неиспользуемый код и другие проблемы до его выполнения.

Настройка CI/CD (Continuous Integration / Continuous Deployment) пайплайна для автоматического запуска линтеров и тестов при каждом коммите или pull request является хорошей практикой.

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
