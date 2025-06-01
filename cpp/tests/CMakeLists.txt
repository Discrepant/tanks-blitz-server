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

# Ensure GLOBAL IMPORTED targets from game_server_cpp are found/usable
if(NOT TARGET RabbitMQC::rabbitmq-c)
    message(FATAL_ERROR "Tests: RabbitMQC::rabbitmq-c target not found. It should be defined as GLOBAL in game_server_cpp.")
else()
    message(STATUS "Tests: Found GLOBAL target RabbitMQC::rabbitmq-c.")
endif()

if(NOT TARGET RdKafka::rdkafka++)
    message(FATAL_ERROR "Tests: RdKafka::rdkafka++ target not found. It should be defined as GLOBAL in game_server_cpp.")
else()
    message(STATUS "Tests: Found GLOBAL target RdKafka::rdkafka++.")
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
    RabbitMQC::rabbitmq-c      # Use consistent GLOBAL target
    RdKafka::rdkafka++         # Use consistent GLOBAL target
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
