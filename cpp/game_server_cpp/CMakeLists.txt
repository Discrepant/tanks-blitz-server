# CMakeLists.txt for game_server_cpp

if(DEFINED VCPKG_TARGET_TRIPLET AND VCPKG_TARGET_TRIPLET)
    set(MY_USING_VCPKG TRUE)
    message(STATUS "GameServerCpp: MY_USING_VCPKG set to TRUE (VCPKG_TARGET_TRIPLET is '${VCPKG_TARGET_TRIPLET}')")
else()
    set(MY_USING_VCPKG FALSE)
    message(STATUS "GameServerCpp: MY_USING_VCPKG set to FALSE (VCPKG_TARGET_TRIPLET is not defined or empty)")
endif()

# CMAKE_CXX_STANDARD is set in the root CMakeLists.txt
if(NOT MY_USING_VCPKG)
  find_package(PkgConfig REQUIRED)
endif()

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

if(MY_USING_VCPKG)
  message(STATUS "GameServerCpp: Attempting to find RdKafka via vcpkg (CONFIG mode).")
  find_package(RdKafka CONFIG REQUIRED) # vcpkg should provide this
  # Vcpkg should define RdKafka::rdkafka (C) and RdKafka::rdkafka++ (C++)
  # We need RdKafka::rdkafka++
  if(TARGET RdKafka::rdkafka++)
    message(STATUS "GameServerCpp: Found RdKafka::rdkafka++ via vcpkg.")
    # Vcpkg targets are typically already global if installed correctly
  else()
    message(FATAL_ERROR "GameServerCpp: RdKafka::rdkafka++ target not found via vcpkg. Ensure rdkafka[cpp] is installed.")
  endif()
else()
  # Существующая логика с find_package QUIET и откатом к pkg-config
  message(STATUS "GameServerCpp: Not using vcpkg. Attempting find_package/pkg-config for RdKafka.")
  find_package(RdKafka CONFIG QUIET)
  if(NOT RdKafka_FOUND)
    find_package(RdKafka QUIET)
  endif()

  if(RdKafka_FOUND AND TARGET RdKafka::rdkafka++)
    message(STATUS "GameServerCpp: Found RdKafka using find_package (target RdKafka::rdkafka++ exists).")
  else() # Not found by find_package or C++ target missing
    message(STATUS "GameServerCpp: RdKafka C++ bindings not found via find_package. Attempting pkg-config.")
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
      pkg_check_modules(PC_RdKafkaCpp QUIET rdkafka++) # Get variables
      if(PC_RdKafkaCpp_FOUND)
        message(STATUS "GameServerCpp: Found RdKafka (rdkafka++) via pkg-config. Version: ${PC_RdKafkaCpp_VERSION}")
        message(STATUS "GameServerCpp: DEBUG PC_RdKafkaCpp_INCLUDE_DIRS = ${PC_RdKafkaCpp_INCLUDE_DIRS}")
        message(STATUS "GameServerCpp: DEBUG PC_RdKafkaCpp_LIBRARIES = ${PC_RdKafkaCpp_LIBRARIES}")
        if(NOT TARGET RdKafka::rdkafka++) # If not found by find_package above
          add_library(RdKafka::rdkafka++ INTERFACE IMPORTED GLOBAL)
          target_include_directories(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_INCLUDE_DIRS})
          target_link_libraries(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_LIBRARIES})
          message(STATUS "GameServerCpp: Created GLOBAL IMPORTED target RdKafka::rdkafka++ from pkg-config.")
        endif()
        set(RdKafka_FOUND TRUE)
      else()
        message(STATUS "GameServerCpp: RdKafka (rdkafka++) not found via pkg-config.")
      endif()
    else()
      message(STATUS "GameServerCpp: PkgConfig not found, cannot use it for RdKafka.")
    endif()
  endif()

  if(NOT RdKafka_FOUND OR NOT TARGET RdKafka::rdkafka++)
    message(FATAL_ERROR "GameServerCpp: Failed to find RdKafka C++ library (rdkafka++).")
  # No specific set_property needed here for IMPORTED_GLOBAL if INTERFACE IMPORTED GLOBAL is used,
  # or if find_package (non-vcpkg) creates a suitable global target.
  endif()
endif() # MY_USING_VCPKG

if(MY_USING_VCPKG)
  message(STATUS "GameServerCpp: Attempting to find RabbitMQ-C via vcpkg (CONFIG mode).")

  find_package(rabbitmq-c CONFIG QUIET)
  if (NOT rabbitmq-c_FOUND)
    message(FATAL_ERROR "GameServerCpp: Package rabbitmq-c not found via vcpkg, despite vcpkg hint for librabbitmq. Check vcpkg installation.")
  else()
    message(STATUS "GameServerCpp: Found package rabbitmq-c via vcpkg (likely provided by librabbitmq).")
    set(RABBITMQ_PACKAGE_NAME "rabbitmq-c")
  endif()

  # Проверка возможных имен целей
  set(RABBITMQ_TARGET_FOUND FALSE)
  set(POSSIBLE_TARGET_NAMES "") # Clear the list
  list(APPEND POSSIBLE_TARGET_NAMES "rabbitmq::rabbitmq" "RabbitMQ::Client")

  foreach(TARGET_NAME ${POSSIBLE_TARGET_NAMES})
    if(TARGET ${TARGET_NAME} AND NOT RABBITMQ_TARGET_FOUND)
      message(STATUS "GameServerCpp: Found RabbitMQ-C target as ${TARGET_NAME} via vcpkg.")
      if(NOT TARGET RabbitMQC::rabbitmq-c)
        add_library(RabbitMQC::rabbitmq-c ALIAS ${TARGET_NAME})
        message(STATUS "GameServerCpp: Aliased ${TARGET_NAME} to RabbitMQC::rabbitmq-c.")
      endif()
      set(RABBITMQ_TARGET_FOUND TRUE)
      break() # Цель найдена, выходим из цикла
    endif()
  endforeach()

  if(NOT RABBITMQ_TARGET_FOUND)
    message(FATAL_ERROR "GameServerCpp: Could not find a suitable RabbitMQ-C target (e.g., rabbitmq::rabbitmq, RabbitMQ::Client) via vcpkg after finding package ${RABBITMQ_PACKAGE_NAME}.")
  endif()

  # Ensure the final target RabbitMQC::rabbitmq-c exists
  if (NOT TARGET RabbitMQC::rabbitmq-c)
      message(FATAL_ERROR "GameServerCpp: Could not establish RabbitMQC::rabbitmq-c target via vcpkg despite previous steps.")
  else()
      message(STATUS "GameServerCpp: Successfully established RabbitMQC::rabbitmq-c target.")
  endif()

else() # NOT MY_USING_VCPKG
  # Существующая логика с find_package QUIET и откатом к pkg-config
  message(STATUS "GameServerCpp: Not using vcpkg. Attempting find_package/pkg-config for RabbitMQ-C.")
  find_package(rabbitmq-c CONFIG QUIET)
  if(NOT rabbitmq-c_FOUND)
    find_package(RabbitMQC QUIET)
  endif()

  if(rabbitmq-c_FOUND AND NOT RabbitMQC_FOUND)
    set(RabbitMQC_FOUND ${rabbitmq-c_FOUND})
    # Check for known vcpkg targets if found this way (though this branch is for NOT MY_USING_VCPKG)
    if(TARGET unofficial-rabbitmq-c::rabbitmq-c AND NOT TARGET RabbitMQC::rabbitmq-c)
        add_library(RabbitMQC::rabbitmq-c ALIAS unofficial-rabbitmq-c::rabbitmq-c)
    elseif(TARGET rabbitmq-c::rabbitmq-c AND NOT TARGET RabbitMQC::rabbitmq-c)
        add_library(RabbitMQC::rabbitmq-c ALIAS rabbitmq-c::rabbitmq-c)
    endif()
  endif()

  if(RabbitMQC_FOUND AND TARGET RabbitMQC::rabbitmq-c)
      message(STATUS "GameServerCpp: Found RabbitMQ-C using find_package.")
  else()
    message(STATUS "GameServerCpp: RabbitMQ-C not found via find_package. Attempting pkg-config.")
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
      pkg_check_modules(PC_RabbitMQC QUIET librabbitmq) # Get variables
      if(PC_RabbitMQC_FOUND)
        message(STATUS "GameServerCpp: Found RabbitMQ-C (librabbitmq) via pkg-config. Version: ${PC_RabbitMQC_VERSION}")
        message(STATUS "GameServerCpp: DEBUG PC_RabbitMQC_INCLUDE_DIRS = ${PC_RabbitMQC_INCLUDE_DIRS}")
        message(STATUS "GameServerCpp: DEBUG PC_RabbitMQC_LIBRARIES = ${PC_RabbitMQC_LIBRARIES}")
        if(NOT TARGET RabbitMQC::rabbitmq-c) # If not found by find_package above
            add_library(RabbitMQC::rabbitmq-c INTERFACE IMPORTED GLOBAL)
            target_include_directories(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_INCLUDE_DIRS})
            target_link_libraries(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_LIBRARIES})
            message(STATUS "GameServerCpp: Created GLOBAL IMPORTED target RabbitMQC::rabbitmq-c from pkg-config.")
        endif()
        set(RabbitMQC_FOUND TRUE)
      else()
        message(STATUS "GameServerCpp: RabbitMQ-C (librabbitmq) not found via pkg-config.")
      endif()
    else()
      message(STATUS "GameServerCpp: PkgConfig not found, cannot use it for RabbitMQ-C.")
    endif()
  endif()

  if(NOT RabbitMQC_FOUND OR NOT TARGET RabbitMQC::rabbitmq-c)
    message(FATAL_ERROR "GameServerCpp: Failed to find RabbitMQ-C library.")
  # No specific set_property needed here for IMPORTED_GLOBAL if INTERFACE IMPORTED GLOBAL is used,
  # or if find_package (non-vcpkg) creates a suitable global target.
  endif()
endif() # MY_USING_VCPKG

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
target_link_libraries(game_logic_lib
    PUBLIC
        Boost::headers # For Asio includes
        Boost::system  # Asio might depend on system
    PRIVATE
        RdKafka::rdkafka++ # Link C++ target
        Threads::Threads
        nlohmann_json::nlohmann_json # If used in .cpp files, not just headers
        RabbitMQC::rabbitmq-c # Use consistent target name
        proto_lib              # For tcp_session using gRPC stubs
)

target_include_directories(game_logic_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RabbitMQC_FOUND>>:${PC_RabbitMQC_INCLUDE_DIRS}>
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RdKafkaCpp_FOUND>>:${PC_RdKafkaCpp_INCLUDE_DIRS}>
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
    # Conditionally add pkg-config include dirs for RabbitMQC if not using vcpkg and found
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RabbitMQC_FOUND>>:${PC_RabbitMQC_INCLUDE_DIRS}>
    # Similarly for RdKafka - though its INTERFACE target should handle this.
    # This is more of a safeguard or for direct includes in main.cpp if any.
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RdKafkaCpp_FOUND>>:${PC_RdKafkaCpp_INCLUDE_DIRS}>
)

install(TARGETS game_server_app DESTINATION bin)

message(STATUS "CMake configuration for game_server_cpp finished.")
