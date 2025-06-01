cmake_minimum_required(VERSION 3.16)
project(TankGameCppServices CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
set(CMAKE_CXX_EXTENSIONS OFF) # Disable compiler-specific extensions like -std=gnu++17

if(MSVC OR (CMAKE_SYSTEM_NAME STREQUAL "Windows" AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang"))
    # Define _WIN32_WINNT to target Windows 10 (0x0A00) or higher.
    # This helps with libraries like Boost.Asio and avoids warnings.
    # For Windows 7, use 0x0601. For Windows 8, use 0x0602. For Windows 8.1, use 0x0603.
    add_compile_definitions(_WIN32_WINNT=0x0A00)
    message(STATUS "Setting _WIN32_WINNT to 0x0A00 (Windows 10)")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Windows" AND CMAKE_CXX_COMPILER_ID MATCHES "Intel")
    # For Intel compiler on Windows, the definition might be different or handled by environment
    add_compile_definitions(_WIN32_WINNT=0x0A00) # Assuming similar for Intel C++ on Windows
    message(STATUS "Setting _WIN32_WINNT to 0x0A00 (Windows 10) for Intel Compiler")
endif()

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
