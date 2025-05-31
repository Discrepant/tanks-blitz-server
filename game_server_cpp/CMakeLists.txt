cmake_minimum_required(VERSION 3.10)
project(GameServerCpp)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

# Find Boost
find_package(Boost REQUIRED COMPONENTS asio)
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


# Add executable
add_executable(game_server_cpp_app
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
)

# Include directories
# Boost and nlohmann_json usually handle their include directories via their CMake targets.
# RabbitMQ include directories are added via PkgConfig::RabbitMQ target properties.
# If specific include directories are still needed:
# target_include_directories(game_server_cpp_app PRIVATE
#     ${Boost_INCLUDE_DIRS}
#     ${RabbitMQ_INCLUDE_DIRS}
#     # Add other include paths if necessary
# )

# Optional: Add compiler flags for more warnings (good practice)
# target_compile_options(game_server_cpp_app PRIVATE -Wall -Wextra -pedantic)

install(TARGETS game_server_cpp_app DESTINATION bin)
