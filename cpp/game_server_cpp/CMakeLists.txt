# CMakeLists.txt for game_server_cpp

# CMAKE_CXX_STANDARD is set in the root CMakeLists.txt

# Find direct dependencies for the game_logic_lib
find_package(Boost 1.71.0 REQUIRED COMPONENTS system)
message(STATUS "GameServerCpp: Found Boost version: ${Boost_VERSION_STRING}")

find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()
if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "GameServerCpp: nlohmann_json not found.")
else()
    message(STATUS "GameServerCpp: Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(RabbitMQ REQUIRED IMPORTED_TARGET librabbitmq) # For CommandConsumer and handlers
if (NOT RabbitMQ_FOUND)
    message(FATAL_ERROR "GameServerCpp: RabbitMQ (librabbitmq-c) not found.")
endif()

pkg_check_modules(RdKafka REQUIRED IMPORTED_TARGET rdkafka++) # For KafkaProducerHandler
if (NOT RdKafka_FOUND)
    message(FATAL_ERROR "GameServerCpp: RdKafka (librdkafka++) not found.")
endif()

find_package(Threads REQUIRED) # For ASIO, gRPC, Kafka, RabbitMQ callbacks etc.

# Define a static library for core game logic and handlers that don't depend on main_auth.cpp specific gRPC client
# This library will be linked by game_server_app and tests.
add_library(game_logic_lib STATIC
    kafka_producer_handler.cpp
    tank.cpp
    tank_pool.cpp
    game_session.cpp    # Added game_session.cpp
    session_manager.cpp # Added session_manager.cpp
    # command_consumer.cpp # To be added when recreated - needs RabbitMQ
)

# Dependencies for game_logic_lib
target_link_libraries(game_logic_lib PRIVATE
    PkgConfig::RdKafka
    PkgConfig::RabbitMQ # If command_consumer is part of this lib
    Threads::Threads
    nlohmann_json::nlohmann_json # If used in .cpp files, not just headers
    Boost::system
)

target_include_directories(game_logic_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR} # So game_server_app can include headers from here
)


# Executable for the main game server
add_executable(game_server_app
    main.cpp
    udp_handler.cpp     # Ensures udp_handler is included
    tcp_handler.cpp     # Ensures tcp_handler is included
    tcp_session.cpp     # Ensures tcp_session is included
    command_consumer.cpp # Added command_consumer.cpp here
)

# Link game_server_app against its constituent libraries and dependencies
target_link_libraries(game_server_app PRIVATE
    game_logic_lib        # Core logic
    auth_grpc_codegen_lib # For gRPC stubs (defined in protos/CMakeLists.txt)
    Boost::system         # For ASIO
    Threads::Threads
    nlohmann_json::nlohmann_json # For JSON processing in handlers
    PkgConfig::RabbitMQ   # For UDP/TCP handlers if they use RabbitMQ directly
    # gRPC::grpc++ and protobuf::libprotobuf are transitive dependencies from auth_grpc_codegen_lib
    # but if GameTCPSession uses gRPC types directly and auth_grpc_codegen_lib doesn't
    # export gRPC::grpc++ as INTERFACE or PUBLIC, we might need to link it here too.
    # Assuming auth_grpc_codegen_lib correctly exports gRPC & Protobuf linkage.
)

target_include_directories(game_server_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} # To find its own headers like udp_handler.h etc.
)

install(TARGETS game_server_app DESTINATION bin)

message(STATUS "CMake configuration for game_server_cpp finished.")
