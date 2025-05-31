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
    Catch2::Catch2WithMain
    game_logic_lib
    auth_grpc_codegen_lib      # For gRPC stubs used in some tests
    nlohmann_json::nlohmann_json
    PkgConfig::RdKafka         # For KafkaProducerHandler in fixtures
    PkgConfig::RabbitMQ        # For CommandConsumer and potentially handlers if tested deeply
    Threads::Threads
    Boost::system              # For Asio sockets in fixtures/tests
    # gRPC and Protobuf libraries are linked via auth_grpc_codegen_lib
    # If more direct gRPC usage (like creating channels in tests):
    gRPC::grpc++_reflection # Optional, for server reflection, if needed
    gRPC::grpc++            # Ensure this is linked if not transitively from auth_grpc_codegen_lib
    protobuf::libprotobuf   # Ensure this is linked if not transitively
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
