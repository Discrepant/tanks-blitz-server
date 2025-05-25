# game_server/metrics.py
from prometheus_client import Gauge, Counter

# Определяем метрики Prometheus
ACTIVE_SESSIONS = Gauge('game_server_active_sessions', 'Number of active game sessions')
TANKS_IN_USE = Gauge('game_server_tanks_in_use', 'Number of tanks currently in use from the pool')
TOTAL_DATAGRAMS_RECEIVED = Counter('game_server_datagrams_received_total', 'Total number of UDP datagrams received')
TOTAL_PLAYERS_JOINED = Counter('game_server_players_joined_total', 'Total number of players joined')

# Эта функция используется в game_server/main.py для обновления Gauge метрик.
# Чтобы избежать циклического импорта SessionManager и TankPool сюда,
# мы оставим эту функцию в game_server.main, но она будет импортировать метрики отсюда.
# Либо, SessionManager и TankPool должны сами обновлять метрики при изменении их состояния.
# Пока оставляем логику обновления метрик в main.py, но метрики определены здесь.

print("Game server metrics defined.")
