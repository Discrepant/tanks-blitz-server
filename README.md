# Tank Battle Game Server

This project is the backend server for a multiplayer tank battle game. It features a microservice architecture with components for authentication and game logic, supporting both Python and C++ implementations for different parts of the system.

## Table of Contents

- [Project Goals](#project-goals)
- [Architecture Overview](#architecture-overview)
- [Directory Structure](#directory-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Contributing](#contributing)
- [Future Improvements](#future-improvements)

## Project Goals

*   Provide a scalable and performant backend for a real-time multiplayer tank battle game.
*   Implement separate services for authentication and game logic.
*   Utilize gRPC for inter-service communication.
*   Employ message queues (Kafka, RabbitMQ) for asynchronous tasks and event streaming.
*   Use Redis for data storage (e.g., user sessions, caching).
*   Support containerized deployment using Docker and orchestration with Kubernetes.
*   Integrate monitoring using Prometheus.
*   Offer both Python and C++ implementations for server components to balance development speed and performance.

## Architecture Overview

The system is designed as a set of microservices:

1.  **Nginx (Conceptual):** Acts as the entry point, handling SSL termination, load balancing, and potentially DDoS protection. It would proxy requests to the appropriate backend services.
    *   TCP traffic for C++ Auth Server.
    *   TCP/UDP traffic for C++ Game Server.

2.  **Authentication Service:**
    *   **C++ TCP Auth Server (`auth_server_cpp`):** Handles client connections (TCP) for login/registration requests. It receives JSON requests and acts as a gRPC client to the Python Auth gRPC Service.
    *   **Python Auth gRPC Service (`auth_server`):** Implements the authentication logic using gRPC. It communicates with Redis (via `user_service.py`) to manage user credentials and publishes authentication events to Kafka.

3.  **Game Service (`game_server_cpp`):**
    *   **C++ Implementation:** Handles core game logic, player movement, combat, and session management.
    *   **Communication:**
        *   Uses TCP for reliable control messages (e.g., login via Game TCP session, which then calls Auth service).
        *   Uses UDP for frequent, low-latency game state updates (e.g., tank positions, actions).
        *   Receives player commands (e.g., move, shoot) via RabbitMQ, processed by `PlayerCommandConsumer`.
        *   Publishes game events (e.g., player scores, match results) to Kafka.

4.  **Message Queues:**
    *   **Kafka:** Used for event streaming and logging from various services (e.g., `auth_events`, `game_events`, `player_sessions_history`). Python and C++ clients are used.
    *   **RabbitMQ:** Used for decoupling producers of player commands (TCP/UDP handlers in C++ Game Server) from consumers (C++ `PlayerCommandConsumer` that applies commands to game logic).

5.  **Redis (`core/redis_client.py`):**
    *   Used by the Python Auth gRPC Service for storing and retrieving user credentials and session information.

6.  **Monitoring (`monitoring/`):**
    *   **Prometheus:** Configured to scrape metrics from application components (primarily Python services, with potential for C++ integration).

## Directory Structure

*   `auth_server/`: Python Auth gRPC service.
    *   `auth_grpc_server.py`: Main gRPC server logic.
    *   `user_service.py`: Handles user data interaction with Redis.
    *   `grpc_generated/`: Python gRPC stubs.
*   `auth_server_cpp/`: C++ TCP Auth server (gRPC client to Python Auth service).
*   `core/`: Shared Python modules (Redis client, Kafka client).
*   `cpp/`: Root for all C++ source code.
    *   `auth_server_cpp/`: (See above)
    *   `game_server_cpp/`: C++ Game Server logic.
    *   `protos/`: Protobuf definition files (`.proto`).
    *   `tests/`: C++ unit tests.
    *   `CMakeLists.txt`: Main CMake file for C++ builds.
*   `deployment/`: Deployment scripts and configurations.
    *   `docker-compose.yml`: For local Docker-based deployment.
    *   `kubernetes/`: Kubernetes manifests.
    *   `nginx/`: Nginx configuration.
*   `game_server/`: Legacy Python game server code (mostly superseded by `game_server_cpp`).
*   `monitoring/`: Prometheus configuration.
*   `protos/`: Shared Protobuf definitions (symlinked or duplicated in `cpp/protos/`).
*   `tests/`: Python automated tests.
    *   `unit/`: Python unit tests.
    *   `load/`: Locust load tests.
    *   `test_integration.py`: Python integration tests.
*   `requirements.txt`: Python dependencies.
*   `pyproject.toml`: Python project configuration.
*   `run_servers.sh`: Script to run (legacy) Python servers.
*   `run_tests.sh`: Script to run Python tests.

## Requirements

**Common:**
*   Git
*   Docker & Docker Compose

**Python Development:**
*   Python 3.9 or newer.
*   See `requirements.txt` for specific package versions (e.g., `grpcio`, `redis`, `confluent-kafka`, `pika`).

**C++ Development:**
*   C++17 compatible compiler (e.g., GCC, Clang).
*   CMake (3.16+ recommended).
*   Boost libraries (Asio, System, Program_options - typically 1.71+).
*   gRPC C++ libraries and development headers (including `grpc_cpp_plugin` for `protoc`).
*   Protocol Buffers C++ libraries, development headers, and `protoc` compiler.
*   `librdkafka-dev` (C/C++ Kafka client library).
*   `librabbitmq-dev` (C client library for RabbitMQ).
*   `nlohmann-json3-dev` (for JSON parsing in C++).
*   `catch2` (for C++ unit tests, v3.x recommended).

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **Setup Python Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Install C++ Dependencies:**
    Installation methods vary by OS. For Debian/Ubuntu:
    ```bash
    sudo apt-get update
    sudo apt-get install -y build-essential cmake libboost-system-dev libboost-program-options-dev \
        libboost-asio-dev nlohmann-json3-dev librabbitmq-dev librdkafka-dev \
        libgrpc++-dev libprotobuf-dev protobuf-compiler grpc_cpp_plugin catch2
    ```
    *Note: Ensure Boost.Asio is installed. If `libboost-asio-dev` is not sufficient or too old, you might need to install a newer Boost version from source or use a package manager like Conan/vcpkg.*
    *Ensure `protoc` and `grpc_cpp_plugin` are in your PATH.*

4.  **Build C++ Components:**
    From the project root:
    ```bash
    cd cpp
    mkdir -p build
    cd build
    cmake ..
    make -j$(nproc) # Adjust -j based on your CPU cores
    ```
    This will build the C++ auth server, game server, and tests. Executables will be in `cpp/build/auth_server_cpp/` and `cpp/build/game_server_cpp/`.

## Running the Application

It's recommended to run backend services like Kafka, RabbitMQ, and Redis using Docker for ease of setup.

### 1. Start Backend Infrastructure (Docker)
If a `docker-compose.yml` is configured for these services:
```bash
docker-compose up -d kafka rabbitmq redis # (Adjust service names as per your docker-compose.yml)
```
Otherwise, start them manually using Docker commands.

### 2. Set Environment Variables
Many components rely on environment variables for configuration (ports, hostnames for Kafka/Redis, etc.). Refer to individual component `main.py` or `main.cpp` files for specifics. Key variables include:
*   `REDIS_HOST`, `REDIS_PORT`
*   `KAFKA_BOOTSTRAP_SERVERS`
*   `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASS`
*   `AUTH_GRPC_PYTHON_PORT` (e.g., `50051`) - For Python Auth gRPC service
*   `AUTH_SERVER_CPP_PORT` (e.g., `9000`) - For C++ TCP Auth server
*   `AUTH_SERVER_CPP_GRPC_TARGET` (e.g., `localhost:50051`) - For C++ TCP Auth server to connect to Python gRPC
*   `GAME_SERVER_CPP_TCP_PORT` (e.g., `8888`)
*   `GAME_SERVER_CPP_UDP_PORT` (e.g., `8889`)

### 3. Run Services Locally (Order Matters)

   a. **Python Auth gRPC Service:**
      ```bash
      # In project root, with venv activated
      export AUTH_GRPC_PYTHON_PORT=50051 KAFKA_BOOTSTRAP_SERVERS=localhost:9092 REDIS_HOST=localhost REDIS_PORT=6379
      python -m auth_server.auth_grpc_server
      ```

   b. **C++ TCP Auth Server:**
      Open a new terminal:
      ```bash
      # From cpp/build/auth_server_cpp/
      export AUTH_SERVER_CPP_GRPC_TARGET=localhost:50051
      ./auth_server_app 9000 ${AUTH_SERVER_CPP_GRPC_TARGET}
      ```
      *(The executable might take arguments directly as shown, or use environment variables if coded to do so).*

   c. **C++ Game Server:**
      Open a new terminal:
      ```bash
      # From cpp/build/game_server_cpp/
      export GAME_TCP_PORT=8888 GAME_UDP_PORT=8889 \
             RABBITMQ_HOST=localhost KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
             AUTH_GRPC_SERVICE_ADDRESS=localhost:50051 # Used by Game TCP session for login
      ./game_server_app
      ```
      *(The C++ game server needs to be implemented to read these environment variables or accept them as command-line arguments).*

### 4. Running with Docker Compose
The main `docker-compose.yml` in the root directory can be used to build and run the Python services. **It needs to be updated to include build steps and service definitions for the C++ components.**
Once updated:
```bash
docker-compose up --build -d
```
Check logs:
```bash
docker-compose logs -f [service_name]
```

## Testing

### Python Tests
The `run_tests.sh` script executes Python unit and integration tests.
```bash
./run_tests.sh
```
This typically runs:
*   **Unit Tests:** `pytest -v tests/unit/`
*   **Integration Tests:** `pytest -v tests/test_integration.py`

**Load Tests (Locust):**
The `run_tests.sh` script also provides instructions for running Locust load tests. Ensure the target server (Auth or Game) is running.
Example for Auth server:
```bash
locust -f tests/load/locustfile_auth.py AuthUser --host http://localhost:8888 # Adjust port if needed
```
Access the Locust UI at `http://localhost:8089`.

### C++ Unit Tests (Catch2)
C++ tests are built during the `make` step in `cpp/build/`.
To run them:
```bash
cd cpp/build/
ctest -V
# OR run the test executable directly
./tests/game_tests # (Or whatever the test executable is named by CMake)
```
*Note: Some C++ tests, especially those interacting with the Auth gRPC service (e.g., `test_auth_tcp_session.cpp`), may require the Python Auth gRPC service to be running.*

## Contributing
Contributions are welcome! Please follow standard practices:
1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes.
4.  Add/update tests.
5.  Ensure all tests pass.
6.  Submit a pull request.

## Future Improvements
*   Complete the `docker-compose.yml` to include C++ services.
*   Implement robust configuration management for C++ services (e.g., using config files or more comprehensive environment variable parsing).
*   Expand C++ unit and integration tests, including mocks for external services.
*   Integrate C++ services with Prometheus for metrics.
*   Enhance game logic and features in the C++ game server.
*   Develop client applications.
