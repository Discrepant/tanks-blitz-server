cmake_minimum_required(VERSION 3.16)
project(AuthGrpcCodegen CXX)

# Find necessary packages for codegen
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED COMPONENTS grpc++)

# Define the location of .proto file
set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/auth_service.proto")

# Set the output directory for generated files within the build directory for this subproject
set(PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${PROTO_GEN_DIR}) # Ensure directory exists

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

add_library(auth_grpc_codegen_lib STATIC
    ${PROTO_SRCS}
    ${GRPC_SRCS}
)

target_include_directories(auth_grpc_codegen_lib
    PUBLIC
        ${PROTO_GEN_DIR}
        ${Protobuf_INCLUDE_DIRS}
        ${gRPC_INCLUDE_DIRS}
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(auth_grpc_codegen_lib
    PUBLIC
        gRPC::grpc++
        ${Protobuf_LIBRARIES}
)

message(STATUS "Configured auth_grpc_codegen_lib target. Generated files will be in ${PROTO_GEN_DIR}")
