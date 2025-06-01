# CMakeLists.txt for auth_server_cpp
# Project and C++ standard are set in the root CMakeLists.txt (cpp/CMakeLists.txt)

# Find Boost (for Asio - system component often needed)
find_package(Boost 1.71.0 REQUIRED COMPONENTS system) # Try finding only system first
if(NOT Boost_FOUND)
    message(FATAL_ERROR "AuthServerCpp: Boost not found.")
else()
    message(STATUS "AuthServerCpp: Found Boost version ${Boost_VERSION_STRING}")
endif()

# Find Threads (for gRPC, Boost Asio, etc.)
find_package(Threads REQUIRED)

# Find nlohmann_json (for JSON processing)
find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()
if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "AuthServerCpp: nlohmann_json not found.")
else()
    message(STATUS "AuthServerCpp: Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

# gRPC and Protobuf dependencies are now expected to be handled by linking
# against the auth_grpc_codegen_lib target defined in cpp/protos/CMakeLists.txt.
# That library should make gRPC and Protobuf headers/libraries available transitively.
# Direct find_package calls for gRPC and Protobuf here are typically not needed
# if auth_grpc_codegen_lib correctly uses PUBLIC/INTERFACE for its dependencies.

add_library(auth_logic_lib STATIC
    auth_tcp_server.cpp
    auth_tcp_session.cpp
)

target_link_libraries(auth_logic_lib PRIVATE
    proto_lib # For gRPC stubs used by auth_tcp_session
    Boost::headers
    Boost::system
    gRPC::grpc++_unsecure # For auth_tcp_session using gRPC
    Threads::Threads
    nlohmann_json::nlohmann_json
)

target_include_directories(auth_logic_lib PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Add executable
add_executable(auth_server_app
    main_auth.cpp
    # auth_tcp_server.cpp # Now in auth_logic_lib
    # auth_tcp_session.cpp # Now in auth_logic_lib
)

# Link libraries
target_link_libraries(auth_server_app
    PRIVATE
    auth_logic_lib # Link the new library
    # proto_lib # Linked by auth_logic_lib
    # Boost::headers # Linked by auth_logic_lib
    # Boost::system  # Linked by auth_logic_lib
    # gRPC::grpc++_unsecure # Linked by auth_logic_lib
    Threads::Threads # main_auth.cpp might still need threads directly
    # nlohmann_json::nlohmann_json # Linked by auth_logic_lib
)

# Include directories
# The include directory for generated gRPC headers (auth_service.grpc.pb.h)
# should come from the auth_grpc_codegen_lib target's PUBLIC include directories.
target_include_directories(auth_server_app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR} # To find its own headers like auth_tcp_session.h
    # If auth_grpc_codegen_lib doesn't correctly export its include dirs:
    # "${CMAKE_BINARY_DIR}/protos/generated" # Path depends on root CMake structure
)

# Install target (optional)
install(TARGETS auth_server_app DESTINATION bin)

message(STATUS "CMake configuration for AuthServerCpp (auth_server_app) finished.")
