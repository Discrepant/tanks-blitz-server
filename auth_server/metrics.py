# auth_server/metrics.py
from prometheus_client import Counter, Gauge

# Счетчик активных соединений
ACTIVE_CONNECTIONS_AUTH = Gauge('auth_server_active_connections', 'Number of active TCP connections to Auth Server')
# Счетчик успешных аутентификаций
SUCCESSFUL_AUTHS = Counter('auth_server_successful_authentications_total', 'Total number of successful authentications')
# Счетчик неудачных аутентификаций
FAILED_AUTHS = Counter('auth_server_failed_authentications_total', 'Total number of failed authentications')

print("Auth server metrics defined.")
