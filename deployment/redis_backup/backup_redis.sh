#!/bin/sh
set -e

BACKUP_DIR="/backups/redis" # Директория для бэкапов внутри контейнера CronJob или на хосте
REDIS_DATA_DIR="/redis-data" # Путь, куда смонтирован PVC от Redis
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RDB_FILE="dump.rdb"
AOF_FILE="appendonly.aof" # Если AOF (Append Only File) включен и используется

mkdir -p ${BACKUP_DIR}

echo "Начало резервного копирования Redis в ${TIMESTAMP}..."

# Копируем RDB файл
if [ -f "${REDIS_DATA_DIR}/${RDB_FILE}" ]; then
    cp "${REDIS_DATA_DIR}/${RDB_FILE}" "${BACKUP_DIR}/dump-${TIMESTAMP}.rdb"
    echo "Резервная копия RDB файла создана: dump-${TIMESTAMP}.rdb"
else
    echo "RDB файл ${REDIS_DATA_DIR}/${RDB_FILE} не найден."
fi

# Копируем AOF файл (если необходимо)
# AOF может быть большим, и его копирование "вживую" может быть не всегда консистентным без BGREWRITEAOF.
# Для AOF лучше использовать команду redis-cli BGREWRITEAOF, чтобы Redis создал свежий, компактный AOF,
# а затем копировать его. Но это усложняет скрипт, так как нужен redis-cli.
# Пока просто копируем существующий файл.
if [ -f "${REDIS_DATA_DIR}/${AOF_FILE}" ]; then
    cp "${REDIS_DATA_DIR}/${AOF_FILE}" "${BACKUP_DIR}/appendonly-${TIMESTAMP}.aof"
    echo "Резервная копия AOF файла создана: appendonly-${TIMESTAMP}.aof"
else
    echo "AOF файл ${REDIS_DATA_DIR}/${AOF_FILE} не найден (это нормально, если AOF отключен или еще не создан)."
fi

echo "Резервное копирование Redis завершено."

# Опционально: Удаление старых бэкапов (например, старше 7 дней)
# find ${BACKUP_DIR} -name "*.rdb" -type f -mtime +7 -delete  # Найти и удалить .rdb файлы старше 7 дней
# find ${BACKUP_DIR} -name "*.aof" -type f -mtime +7 -delete  # Найти и удалить .aof файлы старше 7 дней
# echo "Старые бэкапы удалены."
