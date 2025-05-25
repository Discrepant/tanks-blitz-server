#!/bin/bash

# Скрипт для запуска сервера аутентификации и игрового сервера

# Убедимся, что скрипт запускается из корневой директории проекта
if [ ! -f "auth_server/main.py" ] || [ ! -f "game_server/main.py" ]; then
    echo "Ошибка: Скрипт должен запускаться из корневой директории проекта,"
    echo "где находятся папки auth_server и game_server."
    exit 1
fi

# Функция для проверки, запущен ли процесс на порту
is_port_in_use() {
    if netstat -tuln | grep -q ":$1 "; then
        return 0 # Порт используется
    else
        return 1 # Порт свободен
    fi
}

AUTH_PORT=8888
GAME_PORT=8889

# Проверка портов перед запуском
if is_port_in_use $AUTH_PORT; then
    echo "Порт $AUTH_PORT уже используется. Сервер аутентификации не будет запущен."
    # exit 1 # Можно завершить скрипт или просто пропустить запуск
fi
if is_port_in_use $GAME_PORT; then
    echo "Порт $GAME_PORT уже используется. Игровой сервер не будет запущен."
    # exit 1
fi

# Запуск сервера аутентификации в фоновом режиме
echo "Запуск сервера аутентификации на порту $AUTH_PORT..."
python -m auth_server.main > auth_server.log 2>&1 &
AUTH_PID=$!
echo "Сервер аутентификации запущен с PID: $AUTH_PID. Логи в auth_server.log"

# Небольшая пауза перед запуском следующего сервера
sleep 1

# Запуск игрового сервера в фоновом режиме
echo "Запуск игрового сервера на порту $GAME_PORT..."
python -m game_server.main > game_server.log 2>&1 &
GAME_PID=$!
echo "Игровой сервер запущен с PID: $GAME_PID. Логи в game_server.log"

echo ""
echo "Оба сервера запущены в фоновом режиме."
echo "Для остановки серверов используйте команду 'kill $AUTH_PID $GAME_PID'"
echo "Или остановите их вручную, например, через 'pkill -f auth_server.main' и 'pkill -f game_server.main'"
