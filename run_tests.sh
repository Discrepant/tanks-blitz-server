#!/bin/bash
set -e # Выход при ошибке

echo "Setting PYTHONPATH"
export PYTHONPATH=$PYTHONPATH:.

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running Unit Tests..."
# Для текущей структуры, где auth_server и game_server - пакеты в корне:
pytest -v tests/unit/
echo "Unit Tests Completed."

echo ""
echo "Running Integration Tests..."
# Примечание: Интеграционные тесты могут требовать, чтобы сервисы были запущены
# или доступна специфическая конфигурация окружения.
pytest -v tests/test_integration.py
echo "Integration Tests Completed."

echo ""
echo "All automated tests (Unit and Integration) completed."
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
