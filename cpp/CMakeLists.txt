cmake_minimum_required(VERSION 3.16)
project(TankGameCppServices CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF) # Disable compiler-specific extensions like -std=gnu++17

# Common settings - can be expanded
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) # Useful for some tools like clangd

# Find global dependencies that might be used by multiple subprojects
# For example, if nlohmann_json is used everywhere and version is consistent.
# However, it's often cleaner to let subprojects declare their direct dependencies.

# Add subdirectories
# The 'protos' subdirectory will define a target for gRPC/Protobuf code generation.
# This target can then be linked by other subprojects.
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)
add_subdirectory(protos)
add_subdirectory(game_server_cpp)
add_subdirectory(auth_server_cpp)

# Testing with Catch2
# Enable testing for this project
enable_testing()

# Add the tests subdirectory
# This assumes tests/CMakeLists.txt will define the test executable
add_subdirectory(tests)

message(STATUS "Root CMakeLists.txt processed. Testing enabled.")
