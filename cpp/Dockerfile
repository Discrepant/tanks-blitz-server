# Stage 1: Builder
FROM ubuntu:22.04 AS builder

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Builder stage for Tanks Blitz C++ services"

# Set DEBIAN_FRONTEND to noninteractive to avoid prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies for C++
RUN apt-get update && \
    apt-get install -qq -y \
    build-essential \
    git \
    pkg-config \
    wget \
    tar \
    # Boost (system is often a meta-package, program_options if needed by main, asio is often header-only with newer boost)
    libboost-system-dev \
    libboost-program-options-dev \
    # nlohmann-json (header-only, but -dev package might place it in standard include paths)
    nlohmann-json3-dev \
    # RabbitMQ C client
    librabbitmq-dev \
    # RdKafka C++ client
    librdkafka-dev \
    libc-ares-dev \
    zlib1g-dev \
    # We will build protobuf and grpc from source
    # libgrpc-dev \
    # libgrpc++-dev \
    # libprotobuf-dev \
    # protobuf-compiler \
    # protobuf-compiler-grpc \
    # Catch2 for tests (optional in builder if tests are run outside or in a different stage)
    # catch2 \
    && rm -rf /var/lib/apt/lists/*

RUN    CMAKE_VERSION_MAJOR=3 && \
   CMAKE_VERSION_MINOR=29 && \
   CMAKE_VERSION_PATCH=6 && \
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

# Verify CMake version (optional, but good for debugging)
RUN /usr/local/bin/cmake --version > /tmp/cmake_version.txt && \
    echo "CMake version reported by /usr/local/bin/cmake --version:" && \
    cat /tmp/cmake_version.txt && \
    grep -q "3.29.6" /tmp/cmake_version.txt || \
    (echo "CRITICAL: CMake version is NOT 3.29.6. Actual version in /tmp/cmake_version.txt. Build failed." && exit 1)
RUN echo "CMake version 3.29.6 confirmed by grep."

# Check for CMake policy file
# Note: CMAKE_VERSION_MAJOR and CMAKE_VERSION_MINOR are set within the new RUN command,
# but they are not available as ENV vars for this check unless explicitly set again.
# For simplicity, hardcoding version for this check or re-declaring ENV vars would be needed.
# Assuming the build process correctly places it, the path would be:
# /usr/local/share/cmake-3.28/Modules/CMakePolicyCMP0167.cmake

# Update CA certificates
RUN apt-get update && apt-get install -y --reinstall ca-certificates

# --- Build and install Protobuf v3.21.12 ---
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

# --- Build and install gRPC v1.48.1 ---
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

# --- Build and install Catch2 v3.5.2 ---
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

# Copy the entire content of the current directory (cpp/) into /app/src
# Force rebuild of this layer
# Tue Jun 04 2024 12:00:00 GMT+0000 (Coordinated Universal Time) Force cache invalidation for source copy
COPY . /app/src

# (Остальные шаги типа установки Protobuf, gRPC, Catch2 если они нужны и раскомментированы)
# ...

# Configure and build C++ applications
RUN    echo "Creating build directory for C++ applications..." && \
       mkdir -p /app/src/build_release && \
       cd /app/src/build_release && \
       echo "Configuring C++ applications (cmake)..." && \
       # The main CMakeLists.txt is now at /app/src/cpp/CMakeLists.txt
       /usr/local/bin/cmake -S /app/src/cpp -B . -DCMAKE_BUILD_TYPE=Release && \
       echo "Building C++ applications (make)..." && \
       make -j$(nproc) game_server_app auth_server_app && \
       echo "C++ applications built successfully."

# Stage 2: Runner
FROM ubuntu:22.04 AS runner

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Runner stage for Tanks Blitz C++ services"

ENV DEBIAN_FRONTEND=noninteractive

# Install only runtime dependencies
RUN apt-get update &&     apt-get install -y     libboost-system1.74.0     librabbitmq4     librdkafka++1     libgrpc++1     libprotobuf23     libatomic1     && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -r appgroup && useradd -r -g appgroup -s /sbin/nologin -c "Application User" appuser

# Create work directories
RUN mkdir -p /opt/game_server && \
    mkdir -p /opt/auth_server && \
    chown -R appuser:appgroup /opt/game_server && \
    chown -R appuser:appgroup /opt/auth_server

# Copy compiled executables from builder stage
COPY --from=builder /app/src/build_release/game_server_cpp/game_server_app /opt/game_server/
COPY --from=builder /app/src/build_release/auth_server_cpp/auth_server_app /opt/auth_server/

# Note: Entrypoints/CMDs will be specified in docker-compose.yml for flexibility.
# Example for game_server:
# WORKDIR /opt/game_server
# USER appuser
# ENTRYPOINT ["./game_server_app"]

# Example for auth_server:
# WORKDIR /opt/auth_server
# USER appuser
# ENTRYPOINT ["./auth_server_app"]

# Expose default ports (can be overridden in docker-compose)
# EXPOSE 9000 8888 8889 29998/udp
# Ports are better exposed in docker-compose.yml

STOPSIGNAL SIGTERM

# Basic healthcheck (optional, can be simple command)
# HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
#   CMD exit 0 # Replace with actual health check command for your app if needed
