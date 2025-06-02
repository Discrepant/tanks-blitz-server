cmake_minimum_required(VERSION 3.16)

if(DEFINED VCPKG_TARGET_TRIPLET AND VCPKG_TARGET_TRIPLET)
    set(MY_USING_VCPKG TRUE)
    message(STATUS "Tests: MY_USING_VCPKG set to TRUE (VCPKG_TARGET_TRIPLET is '${VCPKG_TARGET_TRIPLET}')")
else()
    set(MY_USING_VCPKG FALSE)
    message(STATUS "Tests: MY_USING_VCPKG set to FALSE (VCPKG_TARGET_TRIPLET is not defined or empty)")
endif()

project(GameLogicTests CXX)

# CMAKE_CXX_STANDARD is inherited from the root CMakeLists.txt
# find_package(PkgConfig REQUIRED) # No longer directly calling pkg_check_modules here

# Find essential dependencies also needed for tests
find_package(Boost 1.71.0 REQUIRED COMPONENTS system) # Assuming system is needed, add others if necessary
find_package(nlohmann_json 3 REQUIRED) # Or whatever version you expect

# Find RabbitMQ-C (provided by librabbitmq)
if(MY_USING_VCPKG)
  find_package(rabbitmq-c CONFIG QUIET) # Package name is rabbitmq-c as hinted by vcpkg for librabbitmq
  if(NOT rabbitmq-c_FOUND)
    message(FATAL_ERROR "Tests: rabbitmq-c package (expected to be provided by librabbitmq) not found via vcpkg.")
  else()
    message(STATUS "Tests: Found rabbitmq-c package (likely provided by librabbitmq).")
    if(NOT TARGET rabbitmq::rabbitmq) # Check for the actual target name
      message(FATAL_ERROR "Tests: Target rabbitmq::rabbitmq not found after finding rabbitmq-c package.")
    else()
      message(STATUS "Tests: Successfully found target rabbitmq::rabbitmq.")
    endif()
  endif()
else() # NOT MY_USING_VCPKG for RabbitMQ-C
  message(STATUS "Tests: Not using vcpkg. Attempting find_package/pkg-config for RabbitMQ-C.")
  # Attempt to find via find_package first (might find system-installed versions not via vcpkg's specific config)
  find_package(rabbitmq-c CONFIG QUIET) # Try CMake's config mode
  if(NOT rabbitmq-c_FOUND)
    find_package(RabbitMQC QUIET) # Try module mode (e.g. FindRabbitMQC.cmake)
  endif()

  # If find_package found rabbitmq-c and created a target like rabbitmq::rabbitmq or RabbitMQ::Client
  # (adjust based on what find_package might create for non-vcpkg setups if different from RabbitMQC::rabbitmq-c)
  # For consistency with vcpkg block, we want rabbitmq::rabbitmq
  if(rabbitmq-c_FOUND AND TARGET rabbitmq-c::rabbitmq-c AND NOT TARGET rabbitmq::rabbitmq)
    add_library(rabbitmq::rabbitmq ALIAS rabbitmq-c::rabbitmq-c)
    message(STATUS "Tests: Aliased rabbitmq-c::rabbitmq-c to rabbitmq::rabbitmq.")
    set(RabbitMQC_FOUND TRUE) # Consider it found for simplicity
  elseif(RabbitMQC_FOUND AND TARGET RabbitMQC::rabbitmq-c AND NOT TARGET rabbitmq::rabbitmq)
    add_library(rabbitmq::rabbitmq ALIAS RabbitMQC::rabbitmq-c)
    message(STATUS "Tests: Aliased RabbitMQC::rabbitmq-c to rabbitmq::rabbitmq.")
  endif()

  if(TARGET rabbitmq::rabbitmq)
      message(STATUS "Tests: Found RabbitMQ-C using find_package resulting in rabbitmq::rabbitmq target.")
  else() # Not found by find_package or target not named rabbitmq::rabbitmq
    message(STATUS "Tests: RabbitMQ-C not found via find_package suitable for rabbitmq::rabbitmq. Attempting pkg-config for librabbitmq.")
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
      pkg_check_modules(PC_RabbitMQC QUIET librabbitmq) # Get variables for librabbitmq
      if(PC_RabbitMQC_FOUND)
        message(STATUS "Tests: Found RabbitMQ-C (librabbitmq) via pkg-config. Version: ${PC_RabbitMQC_VERSION}")
        message(STATUS "Tests: DEBUG PC_RabbitMQC_INCLUDE_DIRS = ${PC_RabbitMQC_INCLUDE_DIRS}")
        message(STATUS "Tests: DEBUG PC_RabbitMQC_LIBRARIES = ${PC_RabbitMQC_LIBRARIES}")
        # Create an IMPORTED INTERFACE target RabbitMQC::rabbitmq-c
        # Then alias rabbitmq::rabbitmq to it for consistency with vcpkg branch logic
        if(NOT TARGET RabbitMQC::rabbitmq-c)
            add_library(RabbitMQC::rabbitmq-c INTERFACE IMPORTED GLOBAL) # GLOBAL if other test components might need it
            target_include_directories(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_INCLUDE_DIRS})
            target_link_libraries(RabbitMQC::rabbitmq-c INTERFACE ${PC_RabbitMQC_LIBRARIES})
            message(STATUS "Tests: Created GLOBAL IMPORTED target RabbitMQC::rabbitmq-c from pkg-config for librabbitmq.")
        endif()
        if(NOT TARGET rabbitmq::rabbitmq)
            add_library(rabbitmq::rabbitmq ALIAS RabbitMQC::rabbitmq-c)
            message(STATUS "Tests: Aliased RabbitMQC::rabbitmq-c to rabbitmq::rabbitmq.")
        endif()
        set(RabbitMQC_FOUND TRUE) # Mark as found
      else()
        message(STATUS "Tests: RabbitMQ-C (librabbitmq) not found via pkg-config.")
      endif()
    else()
      message(STATUS "Tests: PkgConfig not found, cannot use it for RabbitMQ-C.")
    endif()
  endif()

  if(NOT TARGET rabbitmq::rabbitmq) # Final check for the desired target
    message(FATAL_ERROR "Tests: Failed to find RabbitMQ-C library (target rabbitmq::rabbitmq).")
  else()
    message(STATUS "Tests: Successfully configured RabbitMQ-C (rabbitmq::rabbitmq) for non-vcpkg build.")
  endif()
endif()

# Find RdKafka
if(MY_USING_VCPKG)
  find_package(RdKafka CONFIG QUIET) # vcpkg should provide this
  if(NOT RdKafka_FOUND)
    message(FATAL_ERROR "Tests: RdKafka package not found via vcpkg.")
  else()
    message(STATUS "Tests: Found RdKafka package.") # Added message for package found
    if(NOT TARGET RdKafka::rdkafka++)
      message(FATAL_ERROR "Tests: Target RdKafka::rdkafka++ not found after finding RdKafka package.")
    else()
      message(STATUS "Tests: Successfully found target RdKafka::rdkafka++.")
    endif()
  endif()
else() # NOT MY_USING_VCPKG for RdKafka
  message(STATUS "Tests: Not using vcpkg. Attempting find_package/pkg-config for RdKafka.")
  find_package(RdKafka CONFIG QUIET) # Try CMake's config mode
  if(NOT RdKafka_FOUND)
    find_package(RdKafka QUIET) # Try module mode (e.g. FindRdKafka.cmake)
  endif()

  if(RdKafka_FOUND AND TARGET RdKafka::rdkafka++)
    message(STATUS "Tests: Found RdKafka using find_package (target RdKafka::rdkafka++ exists).")
  else() # Not found by find_package or C++ target missing
    message(STATUS "Tests: RdKafka C++ bindings not found via find_package. Attempting pkg-config for rdkafka++.")
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
      pkg_check_modules(PC_RdKafkaCpp QUIET rdkafka++) # Get variables for rdkafka++
      if(PC_RdKafkaCpp_FOUND)
        message(STATUS "Tests: Found RdKafka (rdkafka++) via pkg-config. Version: ${PC_RdKafkaCpp_VERSION}")
        message(STATUS "Tests: DEBUG PC_RdKafkaCpp_INCLUDE_DIRS = ${PC_RdKafkaCpp_INCLUDE_DIRS}")
        message(STATUS "Tests: DEBUG PC_RdKafkaCpp_LIBRARIES = ${PC_RdKafkaCpp_LIBRARIES}")
        if(NOT TARGET RdKafka::rdkafka++) # If not found by find_package above
          add_library(RdKafka::rdkafka++ INTERFACE IMPORTED GLOBAL) # GLOBAL if needed by other components
          target_include_directories(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_INCLUDE_DIRS})
          target_link_libraries(RdKafka::rdkafka++ INTERFACE ${PC_RdKafkaCpp_LIBRARIES})
          message(STATUS "Tests: Created GLOBAL IMPORTED target RdKafka::rdkafka++ from pkg-config.")
        endif()
        set(RdKafka_FOUND TRUE) # Mark as found
      else()
        message(STATUS "Tests: RdKafka (rdkafka++) not found via pkg-config.")
      endif()
    else()
      message(STATUS "Tests: PkgConfig not found, cannot use it for RdKafka.")
    endif()
  endif()

  if(NOT RdKafka_FOUND OR NOT TARGET RdKafka::rdkafka++)
    message(FATAL_ERROR "Tests: Failed to find RdKafka C++ library (rdkafka++).")
  else()
    message(STATUS "Tests: Successfully configured RdKafka (RdKafka::rdkafka++) for non-vcpkg build.")
  endif()
endif()

find_package(Threads REQUIRED)

# Protobuf and gRPC (even if linked via a library, finding them ensures targets are available)
# We expect these to be found from /usr/local as we built them from source
# find_package(Protobuf CONFIG REQUIRED) # Should be found by top-level or gRPC
find_package(gRPC CONFIG REQUIRED COMPONENTS grpc++) # Or just grpc++ if that's the component name

# Find Catch2
# This requires Catch2 to be installed in a way CMake can find it (e.g., system-wide, or CMAKE_PREFIX_PATH set)
# For Catch2 v3.x, it's often found as a CMake config package.
find_package(Catch2 3 REQUIRED) # This line is already there
if(NOT Catch2_FOUND)
    message(FATAL_ERROR "Catch2 version 3 or later not found. Please install Catch2 development files.")
else()
    message(STATUS "Found Catch2 version: ${Catch2_VERSION}")
endif()

# Add the test executable
add_executable(game_tests
    main_test.cpp
    test_tank.cpp
    test_tank_pool.cpp
    test_game_session.cpp
    test_session_manager.cpp
    test_command_consumer.cpp   # Added
    test_auth_tcp_session.cpp   # Added
    test_game_udp_handler.cpp   # Added
    test_game_tcp_session.cpp   # Added
)

# Link the test executable against Catch2 and the game logic library
# game_logic_lib is defined in ../game_server_cpp/CMakeLists.txt
# auth_grpc_codegen_lib is defined in ../protos/CMakeLists.txt
target_link_libraries(game_tests
    PRIVATE
    Catch2::Catch2WithMain       # Provided by find_package(Catch2)
    game_logic_lib
    auth_logic_lib             # Link the new auth library
    proto_lib      # Changed from auth_grpc_codegen_lib

    # Explicitly link what's directly used by tests, if not covered by game_logic_lib or proto_lib
    Boost::system              # Provided by find_package(Boost)
    nlohmann_json::nlohmann_json # Provided by find_package(nlohmann_json)
    rabbitmq::rabbitmq # Target for RabbitMQ-C (either from vcpkg or pkg-config)
    RdKafka::rdkafka++ # Target for RdKafka (either from vcpkg or pkg-config)
    Threads::Threads           # Provided by find_package(Threads)

    # It's good practice to also link gRPC and Protobuf if tests use them directly,
    # even if proto_lib also links them.
    gRPC::grpc++_unsecure      # Changed from gRPC::grpc++
    protobuf::libprotobuf      # Changed from Protobuf::libprotobuf
    # gRPC::grpc++_reflection  # Only if reflection is directly used in tests
)

# Include directories for the tests
target_include_directories(game_tests
    PRIVATE
    "${CMAKE_SOURCE_DIR}/game_server_cpp" # To find *.h from game_server_cpp
    "${CMAKE_SOURCE_DIR}/auth_server_cpp" # To find *.h from auth_server_cpp (e.g. auth_tcp_session.h)
    # Conditionally add pkg-config include dirs if not using vcpkg and found
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RabbitMQC_FOUND>>:${PC_RabbitMQC_INCLUDE_DIRS}>
    $<$<AND:$<STREQUAL:${MY_USING_VCPKG},FALSE>,$<BOOL:PC_RdKafkaCpp_FOUND>>:${PC_RdKafkaCpp_INCLUDE_DIRS}>
    # The include path for generated gRPC headers ("auth_service.grpc.pb.h")
    # should come from the auth_grpc_codegen_lib target's PUBLIC include directories.
    # If CMAKE_SOURCE_DIR is cpp/, then protos build dir is CMAKE_BINARY_DIR/protos/generated
    # This should be handled by auth_grpc_codegen_lib's INTERFACE_INCLUDE_DIRECTORIES
)

# Add this test executable to CTest
# The first argument is the name CTest will use for the test.
# The second argument is the name of the CMake target for the test executable.
add_test(NAME GameLogicUnitTests COMMAND game_tests)

message(STATUS "Configured game_tests executable.")
