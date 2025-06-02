# Stage 1: Builder
FROM ubuntu:22.04 AS builder

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Builder stage for Tanks Blitz C++ services"

# Set DEBIAN_FRONTEND to noninteractive to avoid prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies for C++
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    git \
    pkg-config \
    wget \
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

# Attempt to remove any system-installed CMake to avoid conflicts
RUN apt-get remove --purge -y cmake cmake-data || true

# --- Install CMake v3.29.2 ---
ENV CMAKE_VERSION=3.29.2
ENV CMAKE_TAR=cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz
ENV CMAKE_URL=https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/${CMAKE_TAR}
RUN wget ${CMAKE_URL} -O /tmp/${CMAKE_TAR} && \
    tar -xzf /tmp/${CMAKE_TAR} -C /opt && \
    rm /tmp/${CMAKE_TAR} && \
    ln -s /opt/cmake-${CMAKE_VERSION}-linux-x86_64/bin/cmake /usr/local/bin/cmake && \
    ln -s /opt/cmake-${CMAKE_VERSION}-linux-x86_64/bin/ctest /usr/local/bin/ctest && \
    ln -s /opt/cmake-${CMAKE_VERSION}-linux-x86_64/bin/cpack /usr/local/bin/cpack
# Verify CMake installation
RUN cmake --version

# --- Build and install Protobuf v3.21.12 ---
ENV PROTOBUF_VERSION=v3.21.12
RUN git clone --depth 1 --branch ${PROTOBUF_VERSION} https://github.com/protocolbuffers/protobuf.git /tmp/protobuf && \
    cd /tmp/protobuf && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -Dprotobuf_BUILD_TESTS=OFF \
          ../cmake && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/protobuf

# --- Build and install gRPC v1.48.1 ---
ENV GRPC_VERSION=v1.48.1
RUN git clone --depth 1 --branch ${GRPC_VERSION} --recurse-submodules https://github.com/grpc/grpc.git /tmp/grpc && \
    cd /tmp/grpc && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -DgRPC_INSTALL=ON \
          -DgRPC_BUILD_TESTS=OFF \
          -DgRPC_PROTOBUF_PROVIDER=package \
          -DgRPC_ZLIB_PROVIDER=package \
          -DgRPC_CARES_PROVIDER=package \
          -DgRPC_SSL_PROVIDER=package \
          .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/grpc

# --- Build and install Catch2 v3.5.2 ---
ENV CATCH2_VERSION=v3.5.2
RUN git clone --depth 1 --branch ${CATCH2_VERSION} https://github.com/catchorg/Catch2.git /tmp/Catch2 && \
    cd /tmp/Catch2 && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -DCATCH_BUILD_TESTING=OFF \
          .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/Catch2

# Set working directory in the builder stage
WORKDIR /opt/build

# Copy the entire cpp directory content into the build stage
# Assumes Dockerfile is in cpp/ and context is parent of cpp/ (e.g. project root)
# If context is cpp/, then COPY . .
COPY . ./
# If Dockerfile is in project root and context is project root, then COPY ./cpp ./cpp

# Add find commands to locate gRPC CMake config files
RUN echo "=== STARTING GRPC FILE SEARCH ===" && \
    (find /usr -name "*gRPCConfig.cmake*" -o -name "*grpc-config.cmake*" -print && echo "FIND COMMAND SEARCHED SUCCESSFULLY") || echo "FIND COMMAND FINISHED - POTENTIALLY NO FILES FOUND OR ERROR DURING FIND" && \
    echo "=== GRPC FILE SEARCH COMPLETE ==="

# Configure and build C++ applications
RUN mkdir -p ./build_release && \
    cd ./build_release && \
    echo "Confirming CMake version before configuring project:" && \
    cmake --version && \
    echo "Using CMake from /usr/local/bin/cmake for project configuration:" && \
    /usr/local/bin/cmake ../cpp -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) game_server_app auth_server_app

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
COPY --from=builder /opt/build/build_release/game_server_cpp/game_server_app /opt/game_server/
COPY --from=builder /opt/build/build_release/auth_server_cpp/auth_server_app /opt/auth_server/

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
