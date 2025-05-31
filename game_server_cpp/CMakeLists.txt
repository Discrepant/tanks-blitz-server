# project(GameServerCpp) # Project command is now in the root CMakeLists.txt

# CMAKE_CXX_STANDARD is also set in the root CMakeLists.txt

# Find Boost
find_package(Boost 1.71.0 REQUIRED COMPONENTS system) # Asio is often header-only with modern Boost + system
message(STATUS "Found Boost version: ${Boost_VERSION_STRING}")
message(STATUS "Boost include dirs: ${Boost_INCLUDE_DIRS}")
message(STATUS "Boost libraries: ${Boost_LIBRARIES}")


# Find nlohmann_json
find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()

if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "nlohmann_json not found. Please ensure it is installed (e.g., sudo apt-get install nlohmann-json3-dev) and findable by CMake.")
else()
    message(STATUS "Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

# Find RabbitMQ (librabbitmq-c)
find_package(PkgConfig REQUIRED)
pkg_check_modules(RabbitMQ REQUIRED IMPORTED_TARGET rabbitmq)
if (RabbitMQ_FOUND)
    message(STATUS "Found RabbitMQ: ${RabbitMQ_LIBRARIES}")
    message(STATUS "RabbitMQ include dirs: ${RabbitMQ_INCLUDE_DIRS}")
else()
    message(FATAL_ERROR "RabbitMQ (librabbitmq-c) not found. Please install librabbitmq-dev.")
endif()

# Find RdKafka (librdkafka++)
pkg_check_modules(RdKafka REQUIRED IMPORTED_TARGET rdkafka++)
if (RdKafka_FOUND)
    message(STATUS "Found RdKafka: ${RdKafka_LIBRARIES}")
    message(STATUS "RdKafka include dirs: ${RdKafka_INCLUDE_DIRS}")
    message(STATUS "RdKafka version: ${RdKafka_VERSION}")
else()
    message(FATAL_ERROR "RdKafka (librdkafka++) not found. Please install librdkafka-dev.")
endif()

# gRPC and Protobuf are now linked via auth_grpc_codegen_lib,
# but we still need Threads for other parts of Asio or gRPC internals if not pulled by auth_grpc_codegen_lib.
find_package(Threads REQUIRED)

# Define a static library for core game logic
add_library(game_logic_lib STATIC
    kafka_producer_handler.cpp
    tank.cpp
    tank_pool.cpp
    game_session.cpp
    session_manager.cpp
)

# Dependencies for game_logic_lib
target_link_libraries(game_logic_lib PRIVATE
    PkgConfig::RdKafka   # For KafkaProducerHandler
    # nlohmann_json might be needed if json is used internally beyond just headers
    # For now, assume header-only usage or it's pulled by other dependencies.
    # If KafkaProducerHandler or others use Boost or Threads directly, add them here.
    # auth_grpc_codegen_lib is not directly used by these core logic files.
)

# Include directories for game_logic_lib (e.g. if its own headers are structured)
# target_include_directories(game_logic_lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}) # Makes its headers available


# Add executable
add_executable(game_server_app # Renamed for clarity
    main.cpp
    udp_handler.cpp
    # stubs.cpp # Removed stubs
    tcp_handler.cpp
    tcp_session.cpp
    kafka_producer_handler.cpp
    tank.cpp
    tank_pool.cpp
    game_session.cpp
    session_manager.cpp
    command_consumer.cpp
)

# Link libraries
target_link_libraries(game_server_cpp_app
    PRIVATE
    Boost::asio
    nlohmann_json::nlohmann_json
    PkgConfig::RabbitMQ  # Use the imported target from pkg_check_modules
    PkgConfig::RdKafka   # Use the imported target for RdKafka
    # Added gRPC and Protobuf via the codegen library
    auth_grpc_codegen_lib # This should bring gRPC::grpc++ and protobuf::libprotobuf transitively
    Threads::Threads      # Explicitly link Threads
    game_logic_lib        # Link against the new game logic library
)

# Include directories
# Boost, nlohmann_json, PkgConfig modules usually handle their include directories via their CMake targets.
# auth_grpc_codegen_lib PUBLIC include directories should provide the generated proto headers.
target_include_directories(game_server_app PRIVATE
    # If auth_grpc_codegen_lib or game_logic_lib don't correctly export their include dirs:
    # "${CMAKE_BINARY_DIR}/protos/generated"
    # "${CMAKE_CURRENT_SOURCE_DIR}" # If game_logic_lib headers need to be found
)

# Optional: Add compiler flags for more warnings (good practice)
# target_compile_options(game_server_app PRIVATE -Wall -Wextra -pedantic)

install(TARGETS game_server_app DESTINATION bin)
