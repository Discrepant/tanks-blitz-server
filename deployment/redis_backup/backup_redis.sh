#!/bin/sh
set -e

BACKUP_DIR="/backups/redis" # Директория для бэкапов внутри контейнера CronJob или на хосте
REDIS_DATA_DIR="/redis-data" # Путь, куда смонтирован PVC от Redis
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RDB_FILE="dump.rdb"
AOF_FILE="appendonly.aof" # Если AOF включен и используется

mkdir -p ${BACKUP_DIR}

echo "Starting Redis backup at ${TIMESTAMP}..."

# Копируем RDB файл
if [ -f "${REDIS_DATA_DIR}/${RDB_FILE}" ]; then
    cp "${REDIS_DATA_DIR}/${RDB_FILE}" "${BACKUP_DIR}/dump-${TIMESTAMP}.rdb"
    echo "RDB file backup created: dump-${TIMESTAMP}.rdb"
else
    echo "RDB file ${REDIS_DATA_DIR}/${RDB_FILE} not found."
fi

# Копируем AOF файл (если необходимо)
# AOF может быть большим, и его копирование "вживую" может быть не всегда консистентным без BGREWRITEAOF
# Для AOF лучше использовать команду redis-cli BGREWRITEAOF, чтобы Redis создал свежий, компактный AOF,
# а затем копировать его. Но это усложняет скрипт, т.к. нужен redis-cli.
# Пока просто копируем существующий.
if [ -f "${REDIS_DATA_DIR}/${AOF_FILE}" ]; then
    cp "${REDIS_DATA_DIR}/${AOF_FILE}" "${BACKUP_DIR}/appendonly-${TIMESTAMP}.aof"
    echo "AOF file backup created: appendonly-${TIMESTAMP}.aof"
else
    echo "AOF file ${REDIS_DATA_DIR}/${AOF_FILE} not found (this is normal if AOF is disabled or not yet created)."
fi

echo "Redis backup finished."

# Опционально: Удаление старых бэкапов (например, старше 7 дней)
# find ${BACKUP_DIR} -name "*.rdb" -type f -mtime +7 -delete
# find ${BACKUP_DIR} -name "*.aof" -type f -mtime +7 -delete
# echo "Old backups deleted."
