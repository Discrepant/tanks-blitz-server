cmake_minimum_required(VERSION 3.16)
project(AuthGrpcCodegen CXX)

# Find necessary packages for codegen
find_package(Protobuf REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_search_module(PC_GRPC REQUIRED grpc++) # Явно ищем grpc++ через pkg-config
# find_package(gRPC REQUIRED) # Удаляем, так как используем pkg-config напрямую

# Define the location of .proto file
set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/auth_service.proto")

# Set the output directory for generated files within the build directory for this subproject
set(PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${PROTO_GEN_DIR}) # Ensure directory exists

# Generate Protobuf and gRPC C++ sources
# Using protobuf_generate_cpp and grpc_generate_cpp (older CMake syntax)
# or protobuf_generate (newer CMake, requires Protobuf_PROTOC_EXECUTABLE etc to be found)
# Let's try with the explicit commands first, as they are often more direct.

# Ensure protoc executable is found
if(NOT Protobuf_PROTOC_EXECUTABLE)
    message(FATAL_ERROR "Protobuf_PROTOC_EXECUTABLE not found by find_package(Protobuf). Please check your Protobuf installation.")
endif()

# Ensure grpc_cpp_plugin is found
find_program(GRPC_CPP_PLUGIN_EXECUTABLE grpc_cpp_plugin)
if(NOT GRPC_CPP_PLUGIN_EXECUTABLE)
    message(FATAL_ERROR "grpc_cpp_plugin not found. Please ensure it is in your PATH or set GRPC_CPP_PLUGIN_EXECUTABLE.")
endif()

# Generated file names
set(PROTO_SRCS "${PROTO_GEN_DIR}/auth_service.pb.cc")
set(PROTO_HDRS "${PROTO_GEN_DIR}/auth_service.pb.h")
set(GRPC_SRCS "${PROTO_GEN_DIR}/auth_service.grpc.pb.cc")
set(GRPC_HDRS "${PROTO_GEN_DIR}/auth_service.grpc.pb.h")

# Custom command to generate files
add_custom_command(
    OUTPUT ${PROTO_SRCS} ${PROTO_HDRS} ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND ${Protobuf_PROTOC_EXECUTABLE}
            --proto_path=${CMAKE_CURRENT_SOURCE_DIR}
            --cpp_out=${PROTO_GEN_DIR}
            --grpc_out=${PROTO_GEN_DIR}
            --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN_EXECUTABLE}
            ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Generating C++ sources from auth_service.proto"
)

# Add a library target for the generated code
# This library will be linked by other projects (game_server_cpp_app, auth_server_cpp_app)
add_library(auth_grpc_codegen_lib STATIC
    ${PROTO_SRCS}
    ${GRPC_SRCS}
)

# Specify include directories for this library itself (for compiling generated sources)
# and for targets that link against it (INTERFACE).
target_include_directories(auth_grpc_codegen_lib
    PUBLIC
        ${PROTO_GEN_DIR}
        ${Protobuf_INCLUDE_DIRS}
        ${PC_GRPC_INCLUDE_DIRS}     # Используем переменную от pkg_search_module
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
)

# Link the codegen library against gRPC and Protobuf libraries
# This ensures that when other targets link auth_grpc_codegen_lib, they get these dependencies.
target_link_libraries(auth_grpc_codegen_lib
    PUBLIC
        ${PC_GRPC_LIBRARIES}    # Используем переменную от pkg_search_module
        protobuf::libprotobuf
)

message(STATUS "Configured auth_grpc_codegen_lib target. Generated files will be in ${PROTO_GEN_DIR}")
