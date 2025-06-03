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

# Install CMake 3.28.3 from tar.gz
ENV CMAKE_VERSION_MAJOR=3
ENV CMAKE_VERSION_MINOR=28
ENV CMAKE_VERSION_PATCH=3
ENV CMAKE_VERSION_FULL=${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}.${CMAKE_VERSION_PATCH}
ENV CMAKE_TAR_BALL=cmake-${CMAKE_VERSION_FULL}-linux-x86_64.tar.gz
ENV CMAKE_DOWNLOAD_URL=https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION_FULL}/${CMAKE_TAR_BALL}

RUN echo "Starting comprehensive CMake 3.28.3 installation..." && \
    apt-get purge -y --auto-remove cmake cmake-data || echo "CMake (apt) not found or already removed, skipping purge." && \
    rm -f /usr/bin/cmake /usr/local/bin/cmake /usr/bin/cpack /usr/local/bin/ctest || echo "Old cmake binaries not found, skipping rm." && \
    echo "Downloading CMake ${CMAKE_VERSION_FULL}..." && \
    wget ${CMAKE_DOWNLOAD_URL} -O /tmp/${CMAKE_TAR_BALL} && \
    echo "Extracting CMake to /tmp/cmake-install..." && \
    mkdir -p /tmp/cmake-install && \
    tar -xzf /tmp/${CMAKE_TAR_BALL} -C /tmp/cmake-install --strip-components=1 && \
    echo "Copying CMake bin files to /usr/local/bin/ using 'cp -a .../.'" && \
    cp -a /tmp/cmake-install/bin/. /usr/local/bin/ && \
    echo "Removing old CMake share directory (if any) and copying new one using 'cp -a .../.'" && \
    rm -rf /usr/local/share/cmake-${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR} && \
    # Note: The source for share files is /tmp/cmake-install/share, and we want its contents 
    # (which include cmake-3.28, man, etc.) to be copied into /usr/local/share.
    # So, the destination for cmake-3.28 modules should become /usr/local/share/cmake-3.28/Modules
    cp -a /tmp/cmake-install/share/. /usr/local/share/ && \
    echo "Verifying copied file directly after cp -a operations:" && \
    (ls -l /usr/local/share/cmake-${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}/Modules/CMakePolicyCMP0167.cmake && echo "File FOUND by ls -l immediately after cp -a in single RUN") || echo "File NOT found by ls -l immediately after cp -a in single RUN" && \
    (test -f /usr/local/share/cmake-${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}/Modules/CMakePolicyCMP0167.cmake && echo "File FOUND by test -f immediately after cp -a in single RUN") || echo "File NOT found by test -f immediately after cp -a in single RUN" && \
    echo "Listing /usr/local/bin after copy:" && \
    ls -R /usr/local/bin/ && \
    echo "Listing /usr/local/share after copy:" && \
    ls -R /usr/local/share/ && \
    echo "Cleaning up temporary CMake installation files..." && \
    rm /tmp/${CMAKE_TAR_BALL} && \
    rm -rf /tmp/cmake-install && \
    echo "CMake installation and initial verification complete."

# Verify CMake version (optional, but good for debugging)
ENV PATH="/usr/local/bin:${PATH}"
RUN /usr/local/bin/cmake --version > /tmp/cmake_version.txt && \
    echo "CMake version reported by /usr/local/bin/cmake --version:" && \
    cat /tmp/cmake_version.txt && \
    grep -q "3.28.3" /tmp/cmake_version.txt || \
    (echo "CRITICAL: CMake version is NOT 3.28.3. Actual version in /tmp/cmake_version.txt. Build failed." && exit 1)
RUN echo "CMake version 3.28.3 confirmed by grep."

# Check for CMake policy file
RUN test -f /usr/local/share/cmake-${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}/Modules/CMakePolicyCMP0167.cmake || \
    (echo "CRITICAL: CMake policy file /usr/local/share/cmake-${CMAKE_VERSION_MAJOR}.${CMAKE_VERSION_MINOR}/Modules/CMakePolicyCMP0167.cmake NOT FOUND. Build failed." && exit 1)
RUN echo "CMake policy file CMP0167.cmake found."

# Update CA certificates
RUN apt-get update && apt-get install -y --reinstall ca-certificates

# --- Build and install Protobuf v3.21.12 ---
# ENV PROTOBUF_VERSION=v3.21.12
# RUN echo "Cloning Protobuf..." && git clone --depth 1 --branch ${PROTOBUF_VERSION} https://github.com/protocolbuffers/protobuf.git /tmp/protobuf
# RUN echo "Configuring Protobuf (cmake)..." && cd /tmp/protobuf && mkdir build && cd build && \
#     cmake -DCMAKE_BUILD_TYPE=Release \
#           -DCMAKE_INSTALL_PREFIX=/usr/local \
#           -Dprotobuf_BUILD_TESTS=OFF \
#           ../cmake
# RUN echo "Building Protobuf (make)..." && cd /tmp/protobuf/build && \
#     timeout 60m make -j$(nproc) || (echo "Protobuf make timed out or failed" && exit 1)
# RUN echo "Installing Protobuf (make install)..." && cd /tmp/protobuf/build && \
#     make install
# RUN echo "Running ldconfig after Protobuf install..." && ldconfig && \
#     echo "Cleaning up Protobuf source..." && cd / && rm -rf /tmp/protobuf

# --- Build and install gRPC v1.48.1 ---
# ENV GRPC_VERSION=v1.48.1
# RUN echo "Cloning gRPC..." && git clone --depth 1 --branch ${GRPC_VERSION} --recurse-submodules https://github.com/grpc/grpc.git /tmp/grpc
# RUN echo "Configuring gRPC (cmake)..." && cd /tmp/grpc && mkdir build && cd build && \
#     cmake -DCMAKE_BUILD_TYPE=Release \
#           -DCMAKE_INSTALL_PREFIX=/usr/local \
#           -DgRPC_INSTALL=ON \
#           -DgRPC_BUILD_TESTS=OFF \
#           -DgRPC_PROTOBUF_PROVIDER=package \
#           -DgRPC_ZLIB_PROVIDER=package \
#           -DgRPC_CARES_PROVIDER=package \
#           -DgRPC_SSL_PROVIDER=package \
#           ..
# RUN echo "Building gRPC (make)..." && cd /tmp/grpc/build && \
#     timeout 60m make -j$(nproc) || (echo "gRPC make timed out or failed" && exit 1)
# RUN echo "Installing gRPC (make install)..." && cd /tmp/grpc/build && \
#     make install
# RUN echo "Running ldconfig after gRPC install..." && ldconfig && \
#     echo "Cleaning up gRPC source..." && cd / && rm -rf /tmp/grpc

# --- Build and install Catch2 v3.5.2 ---
# ENV CATCH2_VERSION=v3.5.2
# RUN echo "Cloning Catch2..." && git clone --depth 1 --branch ${CATCH2_VERSION} https://github.com/catchorg/Catch2.git /tmp/Catch2
# RUN echo "Configuring Catch2 (cmake)..." && cd /tmp/Catch2 && mkdir build && cd build && \
#     cmake -DCMAKE_BUILD_TYPE=Release \
#           -DCMAKE_INSTALL_PREFIX=/usr/local \
#           -DCATCH_BUILD_TESTING=OFF \
#           ..
# RUN echo "Building Catch2 (make)..." && cd /tmp/Catch2/build && \
#     timeout 60m make -j$(nproc) || (echo "Catch2 make timed out or failed" && exit 1)
# RUN echo "Installing Catch2 (make install)..." && cd /tmp/Catch2/build && \
#     make install
# RUN echo "Running ldconfig after Catch2 install..." && ldconfig && \
#     echo "Cleaning up Catch2 source..." && cd / && rm -rf /tmp/Catch2

# Set working directory in the builder stage
# WORKDIR /opt/build

# Copy the entire cpp directory content into the build stage
# Assumes Dockerfile is in cpp/ and context is parent of cpp/ (e.g. project root)
# If context is cpp/, then COPY . .
# COPY ./cpp ./cpp
# COPY ./protos ./protos
# If Dockerfile is in project root and context is project root, then COPY ./cpp ./cpp

# Add find commands to locate gRPC CMake config files
# RUN echo "=== STARTING GRPC FILE SEARCH ===" && \
#     (find /usr -name "*gRPCConfig.cmake*" -o -name "*grpc-config.cmake*" -print && echo "FIND COMMAND SEARCHED SUCCESSFULLY") || echo "FIND COMMAND FINISHED - POTENTIALLY NO FILES FOUND OR ERROR DURING FIND" && \
#     echo "=== GRPC FILE SEARCH COMPLETE ==="

# Configure and build C++ applications
# RUN echo "Creating build directory for C++ applications..." && \
#     mkdir -p ./build_release && \
#     cd ./build_release && \
#     echo "Configuring C++ applications (cmake)..." && \
#     /usr/local/bin/cmake ../cpp -DCMAKE_BUILD_TYPE=Release && \
#     echo "Building C++ applications (make)..." && \
#     # make -j$(nproc) game_server_app auth_server_app test_runner # Add test_runner if tests are built too
#     make -j$(nproc) game_server_app auth_server_app && \
#     echo "C++ applications built successfully."

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
