# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Копируем сначала файл зависимостей, чтобы использовать кэш Docker
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь исходный код приложения
COPY . .

# Открываем порты, которые будут использоваться серверами
# Сервер аутентификации (TCP)
EXPOSE 8888
# Метрики сервера аутентификации (HTTP)
EXPOSE 8000
# Игровой сервер (UDP)
EXPOSE 9999
# Метрики игрового сервера (HTTP)
EXPOSE 8001

# Команда по умолчанию (можно переопределить при запуске контейнера)
# ENTRYPOINT ["python", "-m"] 
# CMD ["auth_server.main"] # Пример: запуск auth_server по умолчанию

# Лучше использовать ENTRYPOINT с возможностью передавать аргументы для CMD
# Например, ENTRYPOINT ["python", "-m"]
# А затем в Kubernetes указывать args: ["auth_server.main"] или ["game_server.main"]
# Или определить разные CMD и использовать --entrypoint в docker run или command в K8s.

# Для простоты использования с docker run и K8s command, 
# оставим возможность запускать через переменные окружения или аргументы команды.
# Пример команды для запуска:
# docker run <image_name> auth # для сервера аутентификации
# docker run <image_name> game # для игрового сервера

# CMD ["echo", "Please specify 'auth' or 'game' as a command to run the respective server."]
# ENTRYPOINT ["python", "-m"] # Это более гибко, если использовать с args в K8s

# Давайте сделаем так, чтобы можно было запускать через аргументы к entrypoint-скрипту
# Создадим простой entrypoint.sh
COPY deployment/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
