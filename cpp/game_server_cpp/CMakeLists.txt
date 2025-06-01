# CMakeLists.txt for game_server_cpp

# CMAKE_CXX_STANDARD is set in the root CMakeLists.txt
find_package(PkgConfig REQUIRED)

# Find direct dependencies for the game_logic_lib
find_package(Boost 1.71.0 REQUIRED COMPONENTS system) # Try finding only system first
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

pkg_check_modules(RdKafkaCpp REQUIRED IMPORTED_TARGET rdkafka++) # Use rdkafka++
if(TARGET RdKafkaCpp::rdkafka++)
    message(STATUS "GameServerCpp: Found RdKafka via pkg-config (IMPORTED_TARGET for rdkafka++)")
elseif(RdKafkaCpp_FOUND)
    message(STATUS "GameServerCpp: Found RdKafka via pkg-config (variables for rdkafka++). Creating INTERFACE target RdKafka::rdkafka++.")
    # Manually create an interface library if IMPORTED_TARGET is not created by pkg_check_modules
    add_library(RdKafka::rdkafka++ INTERFACE IMPORTED GLOBAL) # GLOBAL so tests can find it
    target_include_directories(RdKafka::rdkafka++ INTERFACE ${RdKafkaCpp_INCLUDE_DIRS})
    set_property(TARGET RdKafka::rdkafka++ PROPERTY INTERFACE_LINK_LIBRARIES "${RdKafkaCpp_LIBRARIES}")
else()
    message(FATAL_ERROR "GameServerCpp: rdkafka++ not found using pkg-config.")
endif()
# message(STATUS "GameServerCpp: Found RdKafka version ${RdKafkaCpp_VERSION}") # If available

pkg_check_modules(RabbitMQC REQUIRED IMPORTED_TARGET librabbitmq) # Changed to librabbitmq
if(NOT TARGET RabbitMQC::librabbitmq AND RabbitMQC_FOUND) # Adjusted target name check
    message(STATUS "GameServerCpp: Found librabbitmq via pkg-config (variables). Creating INTERFACE target.")
    add_library(RabbitMQC::librabbitmq INTERFACE IMPORTED GLOBAL) # Adjusted target name, added GLOBAL
    set_property(TARGET RabbitMQC::librabbitmq PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${RabbitMQC_INCLUDE_DIRS}") # Adjusted target name
    set_property(TARGET RabbitMQC::librabbitmq PROPERTY INTERFACE_LINK_LIBRARIES "${RabbitMQC_LIBRARIES}") # Adjusted target name
elseif(TARGET RabbitMQC::librabbitmq) # Adjusted target name check
    message(STATUS "GameServerCpp: Found librabbitmq via pkg-config (IMPORTED_TARGET).")
else()
    message(FATAL_ERROR "GameServerCpp: librabbitmq not found using pkg-config.")
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
    command_consumer.cpp
    udp_handler.cpp
    tcp_handler.cpp
    tcp_session.cpp
)

# Dependencies for game_logic_lib
target_link_libraries(game_logic_lib PRIVATE
    RdKafka::rdkafka++ # Link C++ target
    Threads::Threads
    nlohmann_json::nlohmann_json # If used in .cpp files, not just headers
    Boost::headers # For Asio includes
    Boost::system  # Asio might depend on system
    RabbitMQC::librabbitmq # Added RabbitMQ link for command_consumer, udp_handler etc.
    proto_lib              # For tcp_session using gRPC stubs
)

target_include_directories(game_logic_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR} # So game_server_app can include headers from here
)


# Executable for the main game server
add_executable(game_server_app
    main.cpp
    # udp_handler.cpp     # Now in game_logic_lib
    # tcp_handler.cpp     # Now in game_logic_lib
    # tcp_session.cpp     # Now in game_logic_lib
    # command_consumer.cpp # Now in game_logic_lib
)

# Link game_server_app against its constituent libraries and dependencies
# Most dependencies are now handled by game_logic_lib
target_link_libraries(game_server_app PRIVATE
    game_logic_lib        # Core logic
    # proto_lib # Linked by game_logic_lib if needed by its components (tcp_session)
    # Boost::headers      # Linked by game_logic_lib
    # Boost::system       # Linked by game_logic_lib
    # RdKafka::rdkafka++  # Linked by game_logic_lib
    # RabbitMQC::librabbitmq # Linked by game_logic_lib
    Threads::Threads # main.cpp might still need threads directly
    # nlohmann_json::nlohmann_json # Linked by game_logic_lib
)

target_include_directories(game_server_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} # To find its own headers like udp_handler.h etc.
    ${RabbitMQC_INCLUDE_DIRS} # Explicitly add RabbitMQC include dirs
)

install(TARGETS game_server_app DESTINATION bin)

message(STATUS "CMake configuration for game_server_cpp finished.")
