#!/bin/bash
set -e # Выход из скрипта при любой ошибке

echo "Установка PYTHONPATH"
export PYTHONPATH=$PYTHONPATH:.

echo "Установка зависимостей..."
pip install -r requirements.txt

echo "Запуск модульных тестов (Unit Tests)..."
# Для текущей структуры, где auth_server и game_server являются пакетами в корневой директории:
pytest -v tests/unit/
echo "Модульные тесты завершены."

echo ""
echo "Запуск интеграционных тестов (Integration Tests)..."
# Примечание: Интеграционные тесты могут требовать, чтобы сервисы были запущены,
# или чтобы была доступна специфическая конфигурация окружения.
pytest -v tests/test_integration.py
echo "Интеграционные тесты завершены."

echo ""
echo "Все автоматизированные тесты (модульные и интеграционные) завершены."
echo ""
echo "Для запуска нагрузочных тестов (пример для Auth Server):"
echo "1. Убедитесь, что Auth Server запущен (например, python -m auth_server.main)."
echo "2. Запустите Locust: locust -f tests/load/locustfile_auth.py AuthUser --host localhost"
echo "   (замените localhost, если сервер находится в другом месте, или удалите --host, если он определен в файле Locust)"
echo "   Откройте http://localhost:8089 в вашем браузере для UI Locust."
echo ""
echo "Для запуска нагрузочных тестов (пример для Game Server):"
echo "1. Убедитесь, что Game Server запущен (например, python -m game_server.main)."
echo "2. Запустите Locust: locust -f tests/load/locustfile_game.py GameUser --host localhost"
