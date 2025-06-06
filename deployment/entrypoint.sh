#!/bin/sh
set -e # Выход из скрипта при любой ошибке

TARGET_SERVER=$1

if [ "$TARGET_SERVER" = "auth" ]; then
  echo "Starting Authentication Server..."
  exec python -m auth_server.main
elif [ "$TARGET_SERVER" = "game" ]; then
  echo "Starting Game Server..."
  exec python -m game_server.main
else
  echo "Error: Unknown target server '$TARGET_SERVER'. Please use 'auth' or 'game'."
  exit 1
fi
