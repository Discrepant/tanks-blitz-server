cmake_minimum_required(VERSION 3.10)
project(AuthServerCpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

# Find Boost (for Asio)
find_package(Boost 1.71.0 REQUIRED COMPONENTS system program_options) # Add components as needed by Asio, system is common
if(Boost_FOUND)
    message(STATUS "Found Boost: ${Boost_INCLUDE_DIRS}")
    target_include_directories(AuthServerCpp PRIVATE ${Boost_INCLUDE_DIRS})
    # Asio is header-only in newer Boost versions, but linking system might be needed
    # For older boost, find_package(Boost REQUIRED COMPONENTS asio) might be used.
    # Let's assume modern Boost where Asio doesn't need separate linking if system is linked.
else()
    message(FATAL_ERROR "Boost not found.")
endif()

# Find Threads (for gRPC and Boost Asio)
find_package(Threads REQUIRED)

# Find nlohmann_json (modern CMake way)
find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()
if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "nlohmann_json not found. Please ensure it is installed (e.g., sudo apt-get install nlohmann-json3-dev) and findable by CMake.")
else()
    message(STATUS "Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

# Find Protobuf
# If installed via system package manager, usually found by CMake's FindProtobuf.
# Otherwise, you might need to set CMAKE_PREFIX_PATH or use FetchContent.
find_package(Protobuf CONFIG REQUIRED) # Modern CMake way via config files
if(NOT Protobuf_FOUND)
    message(FATAL_ERROR "Protobuf not found. Please install libprotobuf-dev and protobuf-compiler.")
else()
    message(STATUS "Found Protobuf: ${Protobuf_LIBRARIES}")
    message(STATUS "Protobuf include_dir: ${Protobuf_INCLUDE_DIRS}") # Might be empty if using targets
endif()

# Find gRPC
# This often requires gRPC to be installed in a way that provides CMake config files.
# Setting CMAKE_PREFIX_PATH to gRPC install location is common.
find_package(gRPC CONFIG REQUIRED)
if(NOT gRPC_FOUND)
    message(FATAL_ERROR "gRPC not found. Please install gRPC development libraries (libgrpc++-dev, grpc-proto).")
else()
    message(STATUS "Found gRPC: ${gRPC_LIBRARIES}") # Might be empty if using targets
    message(STATUS "gRPC include_dir: ${gRPC_INCLUDE_DIRS}") # Might be empty if using targets
endif()

# Add generated protobuf and gRPC files to a variable
# These files are expected to be in grpc_generated/ relative to this CMakeLists.txt
file(GLOB GRPC_GENERATED_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/grpc_generated/auth_service.pb.cc"
    "${CMAKE_CURRENT_SOURCE_DIR}/grpc_generated/auth_service.grpc.pb.cc"
)
# Add include directory for generated files
include_directories("${CMAKE_CURRENT_SOURCE_DIR}/grpc_generated")


# Add executable
add_executable(auth_server_cpp_app
    main_auth.cpp
    auth_tcp_server.cpp
    auth_tcp_session.cpp
    ${GRPC_GENERATED_SRCS} # Add generated sources
)

# Link libraries
# The specific gRPC targets can vary based on installation method (make install vs CMake package).
# Common targets are gRPC::grpc++, gRPC::grpc, gRPC::_grpc or just grpc++.
# For protobuf, it's often protobuf::libprotobuf.
target_link_libraries(auth_server_cpp_app
    PRIVATE
    Boost::system # Required by Asio if not header-only context or for other Boost parts
    # Boost::program_options # If you use it
    Threads::Threads
    nlohmann_json::nlohmann_json
    gRPC::grpc++ # This is a common modern CMake target for gRPC++ library
    # gRPC::address_sorting # Might be needed by gRPC
    # gRPC::gpr # Might be needed by gRPC
    # gRPC::upb # Might be needed by gRPC
    protobuf::libprotobuf # Common modern CMake target for Protobuf
)

# If Boost::asio is a separate target in your Boost version (older):
# target_link_libraries(auth_server_cpp_app PRIVATE Boost::asio)

# If gRPC or Protobuf targets are not found as gRPC::grpc++ or protobuf::libprotobuf,
# you might need to use ${gRPC_LIBRARIES} and ${Protobuf_LIBRARIES} directly,
# though imported targets are preferred.

# Set include directories (if not handled by targets)
# target_include_directories(auth_server_cpp_app PRIVATE
#     ${Boost_INCLUDE_DIRS}
#     ${Protobuf_INCLUDE_DIRS}
#     ${gRPC_INCLUDE_DIRS}
# )

# Install target (optional)
install(TARGETS auth_server_cpp_app DESTINATION bin)

message(STATUS "CMake configuration for AuthServerCpp finished.")
