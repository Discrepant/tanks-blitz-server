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
    *   Протокол: TCP.
    *   Назначение: Регистрация и аутентификация пользователей. В реальной системе генерировал бы сессионные токены.
    *   Технологии: Python, `asyncio`.
    *   Экспортирует метрики для Prometheus на порт `8000`.
4.  **Игровой Сервер (Game Server):**
    *   Протокол: UDP.
    *   Назначение: Обработка игровой логики, синхронизация состояния игры.
    *   Паттерны:
        *   `SessionManager` (Singleton) для управления активными игровыми сессиями.
        *   `TankPool` (Object Pool) для управления объектами танков.
    *   Дельта-обновления: Концептуально заложены (отправка только изменений), но требуют полной реализации.
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

(Краткое описание основных директорий, созданных ранее, например):
- `auth_server/`: Код сервера аутентификации.
- `game_server/`: Код игрового сервера.
- `core/`: Общие модули (например, клиент Redis, модели данных).
- `tests/`: Юнит и нагрузочные тесты.
- `monitoring/`: Конфигурации для Prometheus и Grafana.
- `deployment/`: Dockerfile, скрипты и манифесты Kubernetes, конфигурации Nginx и Redis.

## Требования

- Python 3.9+
- Docker
- `kubectl` (для развертывания в Kubernetes)
- Доступ к кластеру Kubernetes (например, Minikube, Kind, или облачный EKS, GKE, AKS)
- `locust` (для запуска нагрузочных тестов)

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
    *(Примечание: Для UDP важно указать `/udp` при публикации порта)*

## Развертывание в Kubernetes

Все необходимые манифесты находятся в директории `deployment/kubernetes/`.

**Предварительные шаги:**

1.  **Настройте `kubectl`** для работы с вашим кластером Kubernetes.
2.  **Соберите и загрузите Docker образ** (`your_image_name:latest`) в репозиторий образов, доступный вашему кластеру Kubernetes (например, Docker Hub, AWS ECR, Google GCR). Обновите имя образа в файлах `*.deployment.yaml`.
    *   Если вы используете локальный кластер типа Minikube, вы можете собрать образ непосредственно в Docker-демоне Minikube: `eval $(minikube -p minikube docker-env)` перед `docker build`. В этом случае в `imagePullPolicy: IfNotPresent` в Deployment'ах может быть достаточно.

**Порядок развертывания компонентов:**

1.  **ConfigMaps (Nginx, Redis):**
    ```bash
    kubectl apply -f deployment/kubernetes/nginx_configmap.yaml
    kubectl apply -f deployment/kubernetes/redis_configmap.yaml
    ```

2.  **PersistentVolumeClaim для Redis:**
    *Убедитесь, что в вашем кластере настроен StorageClass или доступны PersistentVolumes.*
    ```bash
    kubectl apply -f deployment/kubernetes/redis_pvc.yaml
    ```
    *Дождитесь, пока PVC получит статус `Bound` (`kubectl get pvc redis-pvc`).*

3.  **Redis (Deployment и Service):**
    ```bash
    kubectl apply -f deployment/kubernetes/redis_deployment.yaml
    kubectl apply -f deployment/kubernetes/redis_service.yaml
    ```

4.  **Серверы Приложения (Auth и Game):**
    ```bash
    kubectl apply -f deployment/kubernetes/auth_deployment.yaml
    kubectl apply -f deployment/kubernetes/auth_service.yaml
    kubectl apply -f deployment/kubernetes/game_deployment.yaml
    kubectl apply -f deployment/kubernetes/game_service.yaml
    ```

5.  **Nginx (Deployment и Service LoadBalancer):**
    ```bash
    kubectl apply -f deployment/kubernetes/nginx_deployment.yaml
    kubectl apply -f deployment/kubernetes/nginx_service.yaml
    ```
    *После этого Nginx будет доступен через внешний IP (если используется `type: LoadBalancer` и облачный провайдер его поддерживает). Получите IP: `kubectl get svc nginx-loadbalancer`.*

6.  **Резервное копирование Redis (CronJob):**
    *Внимание: Конфигурация `backup-target-storage` в `redis_backup_cronjob.yaml` использует `emptyDir` в качестве заглушки. Для реальных бэкапов это необходимо заменить на PersistentVolume, подключенный к внешнему хранилищу.*
    ```bash
    kubectl apply -f deployment/kubernetes/redis_backup_cronjob.yaml
    ```

**Доступ к сервисам:**
- После развертывания Nginx с `type: LoadBalancer`, внешний IP-адрес Nginx будет точкой входа для TCP (порт 8888) и UDP (порт 9999) трафика.
- Метрики серверов (Auth:8000, Game:8001) будут доступны внутри кластера через их сервисы или через Nginx, если настроить для них проксирование.

## Мониторинг (Prometheus и Grafana)

1.  **Развертывание Prometheus и Grafana:**
    Проще всего использовать готовые Helm-чарты (например, `kube-prometheus-stack`) или Docker Compose для локального тестирования (см. `docker-compose.yml` в этом README - *необходимо его добавить или сослаться на созданный ранее файл*).
    Предполагается, что Prometheus настроен на сбор метрик с эндпоинтов:
    - Auth Server: `http://auth-server-service:8000/metrics`
    - Game Server: `http://game-server-service:8001/metrics`
    (Конфигурация Prometheus: `monitoring/prometheus/prometheus.yml`)

2.  **Настройка Grafana:**
    - Добавить Prometheus как источник данных (URL: `http://prometheus_service_name:9090`).
    - Импортировать или создать дашборды для визуализации метрик.

## Тестирование

**Юнит-тесты:**
Для запуска юнит-тестов (используется `pytest`):
```bash
# Убедитесь, что вы в корневой директории проекта
# и зависимости установлены
sh run_tests.sh 
# или напрямую:
# pytest -v tests/unit/
```

**Нагрузочные тесты (Locust):**
Требуют запущенных серверов.

1.  **Для сервера аутентификации:**
    - Запустите Auth Server (локально или в Docker).
    - Выполните:
      ```bash
      locust -f tests/load/locustfile_auth.py AuthUser --host <auth_server_host>
      # Например: locust -f tests/load/locustfile_auth.py AuthUser --host localhost
      ```
    - Откройте веб-интерфейс Locust (обычно `http://localhost:8089`).

2.  **Для игрового сервера:**
    - Запустите Game Server (локально или в Docker).
    - Выполните:
      ```bash
      locust -f tests/load/locustfile_game.py GameUser --host <game_server_host>
      # Например: locust -f tests/load/locustfile_game.py GameUser --host localhost
      ```

## Резервное копирование Redis

- Redis настроен на использование RDB снапшотов и AOF логов для персистентности.
- Kubernetes CronJob (`deployment/kubernetes/redis_backup_cronjob.yaml`) настроен для выполнения скрипта резервного копирования (копирование RDB/AOF файлов).
- **Важно:** Место для хранения бэкапов (`backup-target-storage` в CronJob) должно быть настроено на использование надежного внешнего хранилища.

## Дальнейшие улучшения и TODO

- **Полная интеграция базы данных (PostgreSQL)** для сервера аутентификации вместо заглушки.
- **Реализация системы токенов** (JWT) для аутентификации и авторизации между сервисами.
- **Детализированная реализация дельта-обновлений** на игровом сервере.
- **Более сложная игровая логика:** обработка столкновений, физика, разные типы танков и оружия и т.д.
- **Матчмейкинг.**
- **Защищенное хранение секретов** в Kubernetes (например, с помощью Sealed Secrets или HashiCorp Vault).
- **Настройка HTTPS/TLS** для Nginx и эндпоинтов метрик.
- **Более продвинутая конфигурация Nginx** для DDoS-защиты.
- **Логирование:** Централизованный сбор и анализ логов (например, ELK Stack или Grafana Loki).
- **Улучшение скриптов резервного копирования:** использование `redis-cli BGREWRITEAOF`, загрузка в облачные хранилища, стратегии ротации бэкапов.
- **Тестирование восстановления** из бэкапов.
- **Helm-чарт** для упрощения развертывания всего приложения в Kubernetes.

## Названия файлов (ключевые)

- `Dockerfile`: Описание Docker-образа.
- `requirements.txt`: Зависимости Python.
- `auth_server/main.py`: Точка входа сервера аутентификации.
- `game_server/main.py`: Точка входа игрового сервера.
- `deployment/kubernetes/`: Манифесты для развертывания в Kubernetes.
  - `*_deployment.yaml`: Описания развертываний подов.
  - `*_service.yaml`: Описания сервисов для доступа к подам.
  - `nginx_*.yaml`: Конфигурации для Nginx.
  - `redis_*.yaml`: Конфигурации для Redis.
- `monitoring/prometheus/prometheus.yml`: Конфигурация Prometheus.
- `tests/`: Каталог с тестами.
  - `unit/`: Юнит-тесты.
  - `load/`: Нагрузочные тесты Locust.
- `README.md`: Этот файл.
