cmake_minimum_required(VERSION 3.16)
project(GameLogicTests CXX)

# CMAKE_CXX_STANDARD is inherited from the root CMakeLists.txt

# Find Catch2
# This requires Catch2 to be installed in a way CMake can find it (e.g., system-wide, or CMAKE_PREFIX_PATH set)
# For Catch2 v3.x, it's often found as a CMake config package.
find_package(Catch2 3 REQUIRED)
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
    # Add other test_*.cpp files here as they are created
)

# Link the test executable against Catch2 and the game logic library
# game_logic_lib is defined in ../game_server_cpp/CMakeLists.txt
# auth_grpc_codegen_lib is defined in ../protos/CMakeLists.txt
# We need to ensure these targets are visible here.
# The add_subdirectory calls in the root CMakeLists.txt should make them globally visible.
target_link_libraries(game_tests
    PRIVATE
    Catch2::Catch2WithMain # Catch2 v3 provides this target which includes its own main
    game_logic_lib         # Link against our game logic
    # If tests directly or indirectly need gRPC/Protobuf (e.g. KafkaProducerHandler uses nlohmann_json which might be linked by auth_grpc_codegen_lib)
    # And if game_logic_lib does not publicly link everything it needs, we might need them here.
    # For now, assume game_logic_lib handles its direct dependencies.
    # We might need to link against common dependencies like nlohmann_json if not pulled transitively.
    nlohmann_json::nlohmann_json # If Tank/TankPool use json and game_logic_lib doesn't export it
    # We also need kafka, rabbitmq if used by any tested components (KafkaProducerHandler)
    PkgConfig::RdKafka # For KafkaProducerHandler used in tests
    # PkgConfig::RabbitMQ # Not directly used by Tank/TankPool tests
    Threads::Threads # Often needed by async operations or libraries
)

# Include directories for the tests
# This ensures that test_tank.cpp can find "../game_server_cpp/tank.h", etc.
# And also for Catch2 headers if not handled by the target.
target_include_directories(game_tests
    PRIVATE
    "${CMAKE_SOURCE_DIR}/game_server_cpp" # To find tank.h, etc. (assuming CMAKE_SOURCE_DIR is cpp/)
    # Catch2::Catch2WithMain should handle its own include directories.
    # If auth_grpc_codegen_lib headers were needed by game_logic_lib, they should be INTERFACE includes there.
    # For example, if game_logic_lib included something from protos/generated:
    # "${CMAKE_BINARY_DIR}/protos/generated"
)

# Add this test executable to CTest
# The first argument is the name CTest will use for the test.
# The second argument is the name of the CMake target for the test executable.
add_test(NAME GameLogicUnitTests COMMAND game_tests)

message(STATUS "Configured game_tests executable.")
