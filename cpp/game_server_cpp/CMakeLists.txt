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

# Try to find RdKafka using CMake's find_package (vcpkg or system FindRdKafka.cmake)
find_package(RdKafka CONFIG QUIET)
if(NOT RdKafka_FOUND)
  find_package(RdKafka QUIET) # Try basic module mode
endif()

if(RdKafka_FOUND AND TARGET RdKafka::rdkafka++)
  message(STATUS "GameServerCpp: Found RdKafka using find_package (target RdKafka::rdkafka++ exists).")
elseif(RdKafka_FOUND AND TARGET RdKafka::rdkafka) # Check if only C library target found
  message(STATUS "GameServerCpp: Found RdKafka using find_package (target RdKafka::rdkafka exists, C++ target missing).")
  # Potentially try to use this if C++ bindings are header-only on top of C lib, or flag as error/warning.
  # For now, assume RdKafka::rdkafka++ is required.
  # set(RdKafka_FOUND_CPP_BINDINGS FALSE) # Custom flag - This logic path means C++ target wasn't found by find_package
else()
  # set(RdKafka_FOUND_CPP_BINDINGS FALSE) # Custom flag - This logic path means C++ target wasn't found by find_package
endif()

# If RdKafka_FOUND is true here, it means find_package found something.
# We rely on (TARGET RdKafka::rdkafka++) to be the ultimate check.
if(NOT (RdKafka_FOUND AND TARGET RdKafka::rdkafka++))
  message(STATUS "GameServerCpp: RdKafka C++ bindings not found via find_package. Attempting pkg-config.")
  # find_package(PkgConfig QUIET) # Already at the top
  if(PKG_CONFIG_FOUND)
    pkg_check_modules(PC_RdKafkaCpp QUIET rdkafka++) # No IMPORTED_TARGET here, just get vars
    if(PC_RdKafkaCpp_FOUND)
      message(STATUS "GameServerCpp: Found RdKafka (rdkafka++) via pkg-config. Version: ${PC_RdKafkaCpp_VERSION}")
      if(NOT TARGET RdKafka::rdkafka++) # Only if not already defined by find_package
          add_library(RdKafka::rdkafka++ INTERFACE IMPORTED GLOBAL)
          target_include_directories(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_INCLUDE_DIRS})
          target_link_libraries(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_LIBRARIES})
          message(STATUS "GameServerCpp: Created RdKafka::rdkafka++ from pkg-config variables.")
      endif()
      set(RdKafka_FOUND TRUE) # Mark as found
    else()
      message(STATUS "GameServerCpp: RdKafka (rdkafka++) not found via pkg-config.")
    endif()
  else()
    message(STATUS "GameServerCpp: PkgConfig not found, cannot use it for RdKafka.")
  endif()
endif()

if(NOT RdKafka_FOUND OR NOT TARGET RdKafka::rdkafka++)
  message(FATAL_ERROR "GameServerCpp: Failed to find RdKafka C++ library (rdkafka++).")
endif()

# Try to find RabbitMQ-C using CMake's find_package (vcpkg or system FindRabbitMQC.cmake)
find_package(rabbitmq-c CONFIG QUIET) # Common name for vcpkg
if(NOT rabbitmq-c_FOUND)
  find_package(RabbitMQC QUIET) # Alternative common name for Find modules
endif()

# Rename variables for consistency if found by a specific name
if(rabbitmq-c_FOUND AND NOT RabbitMQC_FOUND)
  set(RabbitMQC_FOUND ${rabbitmq-c_FOUND})
  set(RabbitMQC_INCLUDE_DIRS ${rabbitmq-c_INCLUDE_DIRS})
  set(RabbitMQC_LIBRARIES ${rabbitmq-c_LIBRARIES})
  # Vcpkg typically creates an imported target like unofficial-rabbitmq-c::rabbitmq-c or similar
  # We need to ensure a consistent target like RabbitMQC::rabbitmq-c
  # For now, assume if found, a suitable target like RabbitMQC::RabbitMQC or unofficial-rabbitmq-c::rabbitmq-c exists.
  # This part might need adjustment based on actual target names from vcpkg.
  # Let's assume vcpkg creates RabbitMQC::rabbitmq-c
  if(TARGET unofficial-rabbitmq-c::rabbitmq-c AND NOT TARGET RabbitMQC::rabbitmq-c)
      add_library(RabbitMQC::rabbitmq-c ALIAS unofficial-rabbitmq-c::rabbitmq-c)
  endif()
  # If find_package(rabbitmq-c) found it and created a target like rabbitmq-c::rabbitmq-c
  if(TARGET rabbitmq-c::rabbitmq-c AND NOT TARGET RabbitMQC::rabbitmq-c)
      add_library(RabbitMQC::rabbitmq-c ALIAS rabbitmq-c::rabbitmq-c)
  endif()
endif()

if(RabbitMQC_FOUND AND TARGET RabbitMQC::rabbitmq-c) # Or whatever target vcpkg/find module provides
    message(STATUS "GameServerCpp: Found RabbitMQ-C using find_package.")
else()
  message(STATUS "GameServerCpp: RabbitMQ-C not found via find_package. Attempting pkg-config.")
  # find_package(PkgConfig QUIET) # Already at the top
  if(PKG_CONFIG_FOUND)
    pkg_check_modules(PC_RabbitMQC QUIET librabbitmq) # No IMPORTED_TARGET here
    if(PC_RabbitMQC_FOUND)
      message(STATUS "GameServerCpp: Found RabbitMQ-C (librabbitmq) via pkg-config. Version: ${PC_RabbitMQC_VERSION}")
      if(NOT TARGET RabbitMQC::rabbitmq-c) # Create a consistent target name
          add_library(RabbitMQC::rabbitmq-c INTERFACE IMPORTED GLOBAL)
          target_include_directories(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_INCLUDE_DIRS})
          target_link_libraries(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_LIBRARIES})
          message(STATUS "GameServerCpp: Created RabbitMQC::rabbitmq-c from pkg-config variables.")
      endif()
      set(RabbitMQC_FOUND TRUE) # Mark as found
    else()
      message(STATUS "GameServerCpp: RabbitMQ-C (librabbitmq) not found via pkg-config.")
    endif()
  else()
    message(STATUS "GameServerCpp: PkgConfig not found, cannot use it for RabbitMQ-C.")
  endif()
endif()

if(NOT RabbitMQC_FOUND OR NOT TARGET RabbitMQC::rabbitmq-c)
  message(FATAL_ERROR "GameServerCpp: Failed to find RabbitMQ-C library.")
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
    RabbitMQC::rabbitmq-c # Use consistent target name
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
    # RabbitMQC::rabbitmq-c # Linked by game_logic_lib (Corrected target name)
    Threads::Threads # main.cpp might still need threads directly
    # nlohmann_json::nlohmann_json # Linked by game_logic_lib
)

target_include_directories(game_server_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} # To find its own headers like udp_handler.h etc.
    ${RabbitMQC_INCLUDE_DIRS} # Explicitly add RabbitMQC include dirs
)

install(TARGETS game_server_app DESTINATION bin)

message(STATUS "CMake configuration for game_server_cpp finished.")
