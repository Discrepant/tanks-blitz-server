# project(AuthServerCpp CXX) # Project is defined in root CMakeLists.txt
# CMAKE_CXX_STANDARD is set in root CMakeLists.txt

# Find Boost (for Asio) - system component is often needed for Asio's non-header-only parts
find_package(Boost 1.71.0 REQUIRED COMPONENTS system)
if(Boost_FOUND)
    message(STATUS "AuthServerCpp: Found Boost: ${Boost_INCLUDE_DIRS}")
    # No need for target_include_directories here if using modern Boost imported targets or if it's header only for Asio.
    # If Boost::asio target is used, it carries its own include directories.
else()
    message(FATAL_ERROR "AuthServerCpp: Boost not found.")
endif()

# Find Threads (for gRPC and Boost Asio)
find_package(Threads REQUIRED)

# Find nlohmann_json
find_package(nlohmann_json 3.2.0 QUIET)
if(NOT nlohmann_json_FOUND)
    find_package(nlohmann_json 3.0.0 REQUIRED)
endif()
if(NOT nlohmann_json_FOUND)
    message(FATAL_ERROR "AuthServerCpp: nlohmann_json not found.")
else()
    message(STATUS "AuthServerCpp: Found nlohmann_json version ${nlohmann_json_VERSION}")
endif()

# gRPC and Protobuf dependencies are now handled by linking against auth_grpc_codegen_lib.
# That library should make gRPC and Protobuf headers/libraries available.
# So, direct find_package for gRPC and Protobuf might not be strictly needed here IF
# auth_grpc_codegen_lib correctly exports its dependencies (e.g. via PUBLIC/INTERFACE linkage).
# However, it's good practice for a target to find its direct dependencies.
# Let's assume auth_grpc_codegen_lib handles this. If linking fails, these might need to be re-added.
# find_package(Protobuf CONFIG REQUIRED)
# find_package(gRPC CONFIG REQUIRED)


# Add executable
add_executable(auth_server_app # Renamed for clarity
    main_auth.cpp
    auth_tcp_server.cpp
    auth_tcp_session.cpp
    # GRPC_GENERATED_SRCS are no longer compiled here directly.
    # They are part of auth_grpc_codegen_lib.
)

# Link libraries
target_link_libraries(auth_server_app
    PRIVATE
    Boost::system         # For Boost.Asio (if not header-only or for other parts)
    Threads::Threads
    nlohmann_json::nlohmann_json
    auth_grpc_codegen_lib # This links the generated gRPC/Protobuf code and its dependencies (gRPC++, Protobuf)
)

# Include directories
# The include directory for generated gRPC headers (auth_service.grpc.pb.h)
# should come from the auth_grpc_codegen_lib target.
# target_include_directories(auth_server_app PRIVATE
#    # If auth_grpc_codegen_lib doesn't correctly export its include dirs:
#    # "${CMAKE_BINARY_DIR}/protos/generated"
# )

# Install target (optional)
install(TARGETS auth_server_app DESTINATION bin)

message(STATUS "CMake configuration for AuthServerCpp (auth_server_app) finished.")
