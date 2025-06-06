# game_server/metrics.py
# Этот модуль определяет метрики Prometheus для игрового сервера.
# Метрики включают количество активных игровых сессий, количество используемых танков,
# общее число полученных UDP-датаграмм и общее число присоединившихся игроков.

from prometheus_client import Gauge, Counter # Импортируем типы метрик из библиотеки Prometheus

# Определяем метрики Prometheus:

# Gauge (датчик) для отслеживания текущего количества активных игровых сессий.
# 'game_server_active_sessions' - имя метрики.
# 'Количество активных игровых сессий' - описание метрики.
ACTIVE_SESSIONS = Gauge(
    'game_server_active_sessions',
    'Количество активных игровых сессий'
)

# Gauge (датчик) для отслеживания текущего количества танков, используемых из пула.
# 'game_server_tanks_in_use' - имя метрики.
# 'Количество танков, используемых в данный момент из пула' - описание метрики.
TANKS_IN_USE = Gauge(
    'game_server_tanks_in_use',
    'Количество танков, используемых в данный момент из пула'
)

# Counter (счетчик) для общего числа полученных UDP-датаграмм.
# Это кумулятивный счетчик, который только увеличивается.
# 'game_server_datagrams_received_total' - имя метрики.
# 'Общее количество полученных UDP-датаграмм' - описание метрики.
TOTAL_DATAGRAMS_RECEIVED = Counter(
    'game_server_datagrams_received_total',
    'Общее количество полученных UDP-датаграмм'
)

# Counter (счетчик) для общего числа игроков, присоединившихся к серверу.
# 'game_server_players_joined_total' - имя метрики.
# 'Общее количество присоединившихся игроков' - описание метрики.
TOTAL_PLAYERS_JOINED = Counter(
    'game_server_players_joined_total',
    'Общее количество присоединившихся игроков'
)

# Новые метрики для соединений, команд и ошибок
GAME_CONNECTIONS = Gauge(
    'game_server_connections_active',
    'Активные игровые соединения',
    ['handler_type'] # например, 'tcp', 'udp'
)

COMMANDS_PROCESSED = Counter(
    'game_server_commands_processed_total',
    'Общее количество обработанных команд',
    ['handler_type', 'command_name', 'status'] # status: 'success', 'error_auth', 'error_unknown', 'error_format' etc.
)

ERRORS_OCCURRED = Counter(
    'game_server_errors_total',
    'Общее количество возникших ошибок',
    ['handler_type', 'error_type'] # error_type: 'auth_failed', 'read_timeout', 'unknown_command', 'internal_exception' etc.
)


# Примечание по обновлению метрик:
# Функция для обновления Gauge-метрик (ACTIVE_SESSIONS, TANKS_IN_USE)
# обычно находится в `game_server/main.py` или вызывается непосредственно
# из `SessionManager` и `TankPool` при изменении их состояния.
# Это делается для избежания циклических импортов, так как `SessionManager` и `TankPool`
# могут сами импортировать эти метрики для инкрементации Counter-метрик или других нужд.
# Таким образом, данный файл (`metrics.py`) служит центральным местом для определения
# метрик, а их обновление происходит в соответствующих компонентах системы.

# logger.info("Определены метрики для игрового сервера.")
# Заменяем print() на logging, если это необходимо для отладки инициализации.
# В данном случае, логгер не инициализирован глобально в этом файле,
# поэтому явный вызов print/logger.info здесь может быть излишним,
# так как `main.py` уже логирует запуск сервера метрик.
