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
    cmake \
    pkg-config \
    git \
    # Boost (system is often a meta-package, program_options if needed by main, asio is often header-only with newer boost)
    libboost-system-dev \
    libboost-program-options-dev \
    # nlohmann-json (header-only, but -dev package might place it in standard include paths)
    nlohmann-json3-dev \
    # RabbitMQ C client
    librabbitmq-dev \
    # RdKafka C++ client
    librdkafka-dev \
    # gRPC and Protocol Buffers
    libgrpc-dev \
    libgrpc++-dev \
    libprotobuf-dev \
    protobuf-compiler \
    protobuf-compiler-grpc \
    # Catch2 for tests (optional in builder if tests are run outside or in a different stage)
    # catch2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory in the builder stage
WORKDIR /opt/build

# Copy the entire cpp directory content into the build stage
# Assumes Dockerfile is in cpp/ and context is parent of cpp/ (e.g. project root)
# If context is cpp/, then COPY . .
COPY . ./
# If Dockerfile is in project root and context is project root, then COPY ./cpp ./cpp

# Configure and build C++ applications
RUN rm -rf ./build_release && \
    mkdir -p ./build_release && \
    cd ./build_release && \
    cmake ../cpp -DCMAKE_BUILD_TYPE=Release && \
    # make -j$(nproc) game_server_app auth_server_app test_runner # Add test_runner if tests are built too
    make -j$(nproc) game_server_app auth_server_app

# Stage 2: Runner
FROM ubuntu:22.04 AS runner

LABEL maintainer="tanks-blitz-dev-team"
LABEL description="Runner stage for Tanks Blitz C++ services"

ENV DEBIAN_FRONTEND=noninteractive

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install -y \
    libboost-system1.74.0 \
    # libboost-program-options1.74.0 \ # If used by apps
    # nlohmann-json3-dev is header only, not needed for runtime unless packaged differently
    librabbitmq4 librdkafka++1 libgrpc++1 libprotobuf23 libatomic1 \
    && rm -rf /var/lib/apt/lists/*

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
