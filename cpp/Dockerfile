# Этап 1: Сборщик
FROM ubuntu:22.04 AS builder

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Builder stage for Tanks Blitz C++ services" # Этап сборки для C++ сервисов Tanks Blitz

# Установка DEBIAN_FRONTEND в noninteractive для избежания запросов во время apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Установка зависимостей сборки для C++
RUN apt-get update && \
    apt-get install -qq -y \
    build-essential \
    git \
    pkg-config \
    wget \
    tar \
    # Boost (system часто является мета-пакетом, program_options если нужен для main, asio часто header-only с новым boost)
    libboost-system-dev \
    libboost-program-options-dev \
    # nlohmann-json (header-only, но -dev пакет может поместить его в стандартные пути включения)
    nlohmann-json3-dev \
    # C-клиент RabbitMQ
    librabbitmq-dev \
    # C++ клиент RdKafka
    librdkafka-dev \
    libc-ares-dev \
    zlib1g-dev \
    # Мы будем собирать protobuf и grpc из исходников
    # libgrpc-dev \
    # libgrpc++-dev \
    # libprotobuf-dev \
    # protobuf-compiler \
    # protobuf-compiler-grpc \
    # Catch2 для тестов (опционально в сборщике, если тесты запускаются вне или на другом этапе)
    # catch2 \
    && rm -rf /var/lib/apt/lists/*

# Этот блок создает символические ссылки для заголовков rabbitmq-c, если они установлены в нестандартное место,
# но пакет librabbitmq-dev в Ubuntu 22.04 обычно размещает их корректно.
# Оставлено для совместимости или специфичных случаев.
RUN if [ -f /usr/include/amqp.h ] && [ ! -d /usr/include/rabbitmq-c ]; then \
          echo "Creating symlinks for rabbitmq-c headers..."; \
          mkdir -p /usr/include/rabbitmq-c && \
          ln -sf /usr/include/amqp.h /usr/include/rabbitmq-c/amqp.h && \
          ln -sf /usr/include/amqp_framing.h /usr/include/rabbitmq-c/framing.h && \
          ln -sf /usr/include/amqp_tcp_socket.h /usr/include/rabbitmq-c/tcp_socket.h && \
          if [ -f /usr/include/amqp_ssl_socket.h ]; then \
            ln -sf /usr/include/amqp_ssl_socket.h /usr/include/rabbitmq-c/ssl_socket.h; \
          fi && \
          echo "Symlinks for rabbitmq-c created in /usr/include/rabbitmq-c/"; \
        else \
          echo "Skipping rabbitmq-c symlink creation: /usr/include/rabbitmq-c already exists or /usr/include/amqp.h not found."; \
        fi

# Установка CMake из исходников для получения нужной версии (например, 3.28+)
RUN    CMAKE_VERSION_MAJOR=3 && \
   CMAKE_VERSION_MINOR=30 && \
   CMAKE_VERSION_PATCH=0 && \
   CMAKE_VERSION_FULL=${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}.${CMAKE_VERSION_PATCH} && \
   echo "Downloading CMake ${CMAKE_VERSION_FULL} source..." && \
   wget --no-verbose "https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION_FULL}/cmake-${CMAKE_VERSION_FULL}.tar.gz" -O /tmp/cmake.tar.gz && \
   mkdir -p /tmp/cmake-source && \
   echo "Extracting CMake source..." && \
   tar -xzf /tmp/cmake.tar.gz -C /tmp/cmake-source --strip-components=1 && \
   cd /tmp/cmake-source && \
   echo "Configuring CMake build..." && \
   ./bootstrap --prefix=/usr/local --parallel=$(nproc) && \
   echo "Building CMake..." && \
   make -j$(nproc) && \
   echo "Installing CMake..." && \
   make install && \
   cd / && \
   echo "Cleaning up CMake source and tarball..." && \
   rm -rf /tmp/cmake-source /tmp/cmake.tar.gz && \
   echo "CMake ${CMAKE_VERSION_FULL} installation from source complete."

# Проверка версии CMake (опционально, но полезно для отладки)
RUN /usr/local/bin/cmake --version > /tmp/cmake_version.txt && \
    echo "CMake version reported by /usr/local/bin/cmake --version:" && \
    cat /tmp/cmake_version.txt && \
    grep -q "3.30.0" /tmp/cmake_version.txt || \
    (echo "CRITICAL: CMake version is NOT 3.30.0. Actual version in /tmp/cmake_version.txt. Build failed." && exit 1)
RUN echo "CMake version 3.30.0 confirmed by grep."

# Проверка файла политики CMake
# Примечание: CMAKE_VERSION_MAJOR и CMAKE_VERSION_MINOR устанавливаются в новой команде RUN,
# но они недоступны как переменные окружения для этой проверки, если не установлены снова явно.
# Для простоты, для этой проверки версия будет указана жестко или переменные окружения будут объявлены заново.
# Предполагая, что процесс сборки корректно размещает его, путь будет:
# /usr/local/share/cmake-3.28/Modules/CMakePolicyCMP0167.cmake

# Обновление CA-сертификатов
RUN apt-get update && apt-get install -y --reinstall ca-certificates

# --- Сборка и установка Protobuf v3.21.12 ---
ENV PROTOBUF_VERSION=v3.21.12
RUN echo "Cloning Protobuf..." && git clone --depth 1 --branch ${PROTOBUF_VERSION} https://github.com/protocolbuffers/protobuf.git /tmp/protobuf
RUN echo "Configuring Protobuf (cmake)..." && cd /tmp/protobuf && mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -Dprotobuf_BUILD_TESTS=OFF \
          ../cmake
RUN echo "Building Protobuf (make)..." && cd /tmp/protobuf/build && \
    timeout 60m make -j$(nproc) || (echo "Protobuf make timed out or failed" && exit 1)
RUN echo "Installing Protobuf (make install)..." && cd /tmp/protobuf/build && \
    make install
RUN echo "Running ldconfig after Protobuf install..." && ldconfig && \
    echo "Cleaning up Protobuf source..." && cd / && rm -rf /tmp/protobuf

# --- Сборка и установка gRPC v1.48.1 ---
ENV GRPC_VERSION=v1.48.1
RUN echo "Cloning gRPC..." && git clone --depth 1 --branch ${GRPC_VERSION} --recurse-submodules https://github.com/grpc/grpc.git /tmp/grpc
RUN echo "Configuring gRPC (cmake)..." && cd /tmp/grpc && mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -DgRPC_INSTALL=ON \
          -DgRPC_BUILD_TESTS=OFF \
          -DgRPC_PROTOBUF_PROVIDER=package \
          -DgRPC_ZLIB_PROVIDER=package \
          -DgRPC_CARES_PROVIDER=package \
          -DgRPC_SSL_PROVIDER=package \
          ..
RUN echo "Building gRPC (make)..." && cd /tmp/grpc/build && \
    timeout 60m make -j$(nproc) || (echo "gRPC make timed out or failed" && exit 1)
RUN echo "Installing gRPC (make install)..." && cd /tmp/grpc/build && \
    make install
RUN echo "Running ldconfig after gRPC install..." && ldconfig && \
    echo "Cleaning up gRPC source..." && cd / && rm -rf /tmp/grpc

# --- Сборка и установка Catch2 v3.5.2 ---
ENV CATCH2_VERSION=v3.5.2
RUN echo "Cloning Catch2..." && git clone --depth 1 --branch ${CATCH2_VERSION} https://github.com/catchorg/Catch2.git /tmp/Catch2
RUN echo "Configuring Catch2 (cmake)..." && cd /tmp/Catch2 && mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -DCATCH_BUILD_TESTING=OFF \
          ..
RUN echo "Building Catch2 (make)..." && cd /tmp/Catch2/build && \
    timeout 60m make -j$(nproc) || (echo "Catch2 make timed out or failed" && exit 1)
RUN echo "Installing Catch2 (make install)..." && cd /tmp/Catch2/build && \
    make install
RUN echo "Running ldconfig after Catch2 install..." && ldconfig && \
    echo "Cleaning up Catch2 source..." && cd / && rm -rf /tmp/Catch2

WORKDIR /app/src

# Копируем все содержимое текущего каталога (cpp/) в /app/src
# Принудительная пересборка этого слоя
# Tue Jun 04 2024 12:00:00 GMT+0000 (Coordinated Universal Time) Принудительная инвалидация кэша для копирования исходников
COPY . /app/src

# (Остальные шаги типа установки Protobuf, gRPC, Catch2 если они нужны и раскомментированы)
# ...

# Конфигурация и сборка C++ приложений
RUN    echo "Creating build directory for C++ applications..." && \
       mkdir -p /app/src/build_release && \
       cd /app/src/build_release && \
       echo "Configuring C++ applications (cmake)..." && \
       # Основной CMakeLists.txt теперь находится в /app/src/cpp/CMakeLists.txt
       /usr/local/bin/cmake -S /app/src/cpp -B . -DCMAKE_BUILD_TYPE=Release && \
       echo "Building C++ applications (make)..." && \
       make -j$(nproc) game_server_app auth_server_app && \
       echo "C++ applications built successfully."

# Этап 2: Исполнитель
FROM ubuntu:22.04 AS runner

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Runner stage for Tanks Blitz C++ services" # Этап выполнения для C++ сервисов Tanks Blitz

ENV DEBIAN_FRONTEND=noninteractive

# Установка только зависимостей времени выполнения
RUN apt-get update &&     apt-get install -y     libboost-system1.74.0     librabbitmq4     librdkafka++1     libgrpc++1     libprotobuf23     libatomic1     && rm -rf /var/lib/apt/lists/*

# Создание непривилегированного пользователя и группы
RUN groupadd -r appgroup && useradd -r -g appgroup -s /sbin/nologin -c "Application User" appuser

# Создание рабочих каталогов
RUN mkdir -p /opt/game_server && \
    mkdir -p /opt/auth_server && \
    chown -R appuser:appgroup /opt/game_server && \
    chown -R appuser:appgroup /opt/auth_server

# Копирование скомпилированных исполняемых файлов из этапа сборщика
COPY --from=builder /app/src/build_release/game_server_cpp/game_server_app /opt/game_server/
COPY --from=builder /app/src/build_release/auth_server_cpp/auth_server_app /opt/auth_server/

# Примечание: Entrypoints/CMDs будут указаны в docker-compose.yml для гибкости.
# Пример для game_server:
# WORKDIR /opt/game_server
# USER appuser
# ENTRYPOINT ["./game_server_app"]

# Пример для auth_server:
# WORKDIR /opt/auth_server
# USER appuser
# ENTRYPOINT ["./auth_server_app"]

# Открытие портов по умолчанию (могут быть переопределены в docker-compose)
# EXPOSE 9000 8888 8889 29998/udp
# Порты лучше открывать в docker-compose.yml

STOPSIGNAL SIGTERM

# Базовая проверка работоспособности (опционально, может быть простой командой)
# HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
#   CMD exit 0 # Замените на реальную команду проверки работоспособности вашего приложения, если необходимо
