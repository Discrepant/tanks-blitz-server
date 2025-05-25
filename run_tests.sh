#!/bin/bash
set -e # Выход при ошибке

echo "Running Unit Tests..."
# Запускаем pytest из корневой директории проекта
# Убедимся, что PYTHONPATH настроен так, чтобы тесты могли найти модули приложения
# Если структура проекта стандартная (например, src/auth_server), то pytest обычно находит.
# Если нет, может потребоваться: export PYTHONPATH=$(pwd):$PYTHONPATH

# Для текущей структуры, где auth_server и game_server - пакеты в корне:
pytest -v tests/unit/

echo "Unit Tests Completed."

echo ""
echo "To run Load Tests (example for Auth Server):"
echo "1. Make sure the Auth Server is running (e.g., python -m auth_server.main)."
echo "2. Run Locust: locust -f tests/load/locustfile_auth.py AuthUser --host localhost"
echo "   (replace localhost if server is elsewhere, or remove --host if defined in Locust file)"
echo "   Open http://localhost:8089 in your browser for the Locust UI."
echo ""
echo "To run Load Tests (example for Game Server):"
echo "1. Make sure the Game Server is running (e.g., python -m game_server.main)."
echo "2. Run Locust: locust -f tests/load/locustfile_game.py GameUser --host localhost"
